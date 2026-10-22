"""Golden solution: reconstruct what readers of analytics.orders saw at the as-of time.

Works only from /app (the table files and the incident note). Steps:
 1. Find the committed metadata chain: the longest metadata-log chain. A file
    off it (the dedup job's 09:10 commit) never reached the catalog.
 2. The state at the as-of time is the last committed metadata written by then,
    and its current snapshot (its snapshot log agrees). A rolled-back snapshot
    was not current after the rollback.
 3. That snapshot's manifest list was deleted by expire_snapshots at 11:30, and
    rewrite_manifests at 11:25 merged some of its manifests with newer ones.
    Rebuild its file set entry by entry from the surviving manifests: the live
    entries added by the snapshot or its ancestors (rewritten entries keep their
    original snapshot id and sequence numbers). Check against its summary totals.
 4. Read each file's columns by field id. The table was migrated from Hive:
    the migrated files have no field ids and the old Hive column names, so
    their ids come from the table's name mapping (schema.name-mapping.default).
    They also lack the identity partition column (region), which comes from
    the manifest entry's partition value (null for the Hive default partition:
    Java treats a null partition value as equal to null when it matches deletes
    to partitions),
    before deletes are matched: the Flink deletes are keyed on (order_id, region).
 5. Apply deletes by the v2 scan rules, using each entry's data sequence number
    (not its file sequence number: compacted files keep the starting snapshot's
    data sequence number). Position deletes need data seq <= delete seq;
    equality deletes need data seq < delete seq; both apply only within the same
    partition spec and partition, where a null partition value equals null (an
    equality delete in an unpartitioned spec would be global; this table has
    none). Null equals null in equality keys too.
 6. Project columns by field id into the snapshot's schema.
"""
import csv
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal

import fastavro
import pyarrow.parquet as pq

TABLE = '/app/warehouse/orders'
AS_OF = datetime(2026, 3, 14, 9, 30, tzinfo=timezone.utc)
OUT = '/app/output/orders_asof.csv'


def local(path, location):
    # The metadata still names the original bucket; the files are under /app.
    assert path.startswith(location), path
    return TABLE + path[len(location):]


def committed_chain():
    """The committed metadata files, oldest first, from evidence on storage.

    Each metadata file lists its predecessors in metadata-log, so the files form
    a tree. A commit only lands if the catalog's compare-and-swap succeeds, so
    two files written from the same base cannot both be committed: the winner
    is the one later commits were built on. The committed chain is the longest
    chain. A file off it (the 09:10 dedup commit: the 10:55 and 11:00 commits
    were built on its sibling) never became current.
    """
    files = sorted(glob.glob(f'{TABLE}/metadata/*.metadata.json'))
    meta = {os.path.basename(f): json.load(open(f)) for f in files}
    referenced = {os.path.basename(e['metadata-file']) for m in meta.values() for e in m.get('metadata-log', [])}
    tips = [f for f in meta if f not in referenced]
    best = max(len(meta[f].get('metadata-log', [])) for f in tips)
    live = [f for f in tips if len(meta[f].get('metadata-log', [])) == best]
    assert len(live) == 1, f'two committed chains of equal length: {live}'
    tip = meta[live[0]]
    return [meta[os.path.basename(e['metadata-file'])] for e in tip['metadata-log']] + [tip]


def resolve_as_of(chain):
    """The state readers saw: the last committed metadata written at or before
    the as-of time, and its current snapshot (equal to its snapshot-log's last
    entry at or before that time). The table's newest metadata no longer lists
    that snapshot: expire_snapshots removed it at 11:30."""
    ms = int(AS_OF.timestamp() * 1000)
    m = [x for x in chain if x['last-updated-ms'] <= ms][-1]
    sid = [e for e in m['snapshot-log'] if e['timestamp-ms'] <= ms][-1]['snapshot-id']
    assert sid == m['current-snapshot-id']
    snap = next(x for x in m['snapshots'] if x['snapshot-id'] == sid)
    schema = next(x for x in m['schemas'] if x['schema-id'] == snap['schema-id'])
    return m, snap, schema


def read_avro(path):
    with open(path, 'rb') as fh:
        return list(fastavro.reader(fh))


def ancestry(snap, chain):
    """The snapshot and its ancestors, from every committed metadata file."""
    parent = {x['snapshot-id']: x.get('parent-snapshot-id') for m in chain for x in m['snapshots']}
    out, sid = set(), snap['snapshot-id']
    while sid is not None:
        out.add(sid)
        sid = parent.get(sid)
    return out


def entries(mf, loc):
    """Live entries of a manifest, with v2 inheritance: an ADDED entry with a
    null snapshot id or sequence number takes it from the manifest list."""
    out = []
    for e in read_avro(local(mf['manifest_path'], loc)):
        if e['status'] == 2:   # DELETED
            continue
        added = e['status'] == 1
        sid = e['snapshot_id'] if e['snapshot_id'] is not None else (mf['added_snapshot_id'] if added else None)
        seq = e['sequence_number'] if e['sequence_number'] is not None else (mf['sequence_number'] if added else None)
        out.append((e, sid, seq))
    return out


def scan(snap, chain):
    """The snapshot's live files. If expiry deleted its manifest list, rebuild
    its file set from the table's surviving manifests: every live entry that
    the snapshot or one of its ancestors added. Rewritten manifests keep each
    entry's original snapshot id and sequence numbers, so this works across
    manifest rewrites. Nothing the ancestors added was removed later (the later
    commits only added files), and the result is checked against the snapshot's
    own summary totals."""
    loc = chain[-1]['location']
    specs = {s['spec-id']: s['fields'] for m in chain for s in m['partition-specs']}
    own = local(snap['manifest-list'], loc)
    if os.path.exists(own):
        picked = [(mf, e, sid, seq) for mf in read_avro(own) for e, sid, seq in entries(mf, loc)]
    else:
        tip = chain[-1]
        survivor = next(x for x in tip['snapshots'] if x['snapshot-id'] == tip['current-snapshot-id'])
        keep = ancestry(snap, chain)
        picked = [(mf, e, sid, seq) for mf in read_avro(local(survivor['manifest-list'], loc))
                  for e, sid, seq in entries(mf, loc) if sid in keep]
    files = []
    for mf, e, sid, seq in picked:
        spec_id = mf['partition_spec_id']
        df = e['data_file']
        part = tuple(df['partition'].get(f['name']) for f in specs[spec_id])
        # Identity partition values, by source field id: a reader fills these
        # columns from the manifest when the file does not hold them.
        constants = {f['source-id']: df['partition'].get(f['name']) for f in specs[spec_id] if f['transform'] == 'identity'}
        files.append({'content': df['content'], 'path': df['file_path'], 'local': local(df['file_path'], loc), 'seq': seq,
                      'spec_id': spec_id, 'unpartitioned': not specs[spec_id], 'part': part, 'records': df['record_count'],
                      'equality_ids': df.get('equality_ids'), 'added_snapshot_id': sid, 'constants': constants})
    summary = snap['summary']
    assert sum(1 for f in files if f['content'] == 0) == int(summary['total-data-files'])
    assert sum(1 for f in files if f['content'] != 0) == int(summary['total-delete-files'])
    assert sum(f['records'] for f in files if f['content'] == 0) == int(summary['total-records'])
    return files


def name_mapping(meta):
    """Column name to field id, from the default name mapping in the metadata
    readers used. Java keeps it in step with the schema: a renamed field keeps
    its Hive name too, and the re-added channel (id 8) took the name from the
    dropped id 5, so the Hive files' channel column reads as field 8."""
    props = meta.get('properties', {})
    mapping = json.loads(props['schema.name-mapping.default'])
    return {name: m['field-id'] for m in mapping for name in m['names']}


def read_columns(path, mapping):
    """Columns of a Parquet file keyed by Iceberg field id. A file with no
    field ids (written by Hive before the migration) gets its ids from the name
    mapping. Read the file itself: pq.read_table on a path under region=... would
    add a partition column inferred from the folder name."""
    t = pq.ParquetFile(path).read()
    by_id = {}
    for i, field in enumerate(t.schema):
        meta = field.metadata or {}
        if b'PARQUET:field_id' in meta:
            fid = int(meta[b'PARQUET:field_id'])
        elif field.name in mapping:
            fid = mapping[field.name]
        else:
            continue   # an unmapped column is not part of the table
        by_id[fid] = t.column(i).to_pylist()
    return by_id, t.num_rows


# The Iceberg v2 scan rules, one function each.

def same_scope(delete, data):
    """A delete applies within its own spec and partition."""
    return delete['spec_id'] == data['spec_id'] and delete['part'] == data['part']


def pos_applies(delete, data):
    return delete['seq'] >= data['seq'] and same_scope(delete, data)


def eq_applies(delete, data):
    # An equality delete in an unpartitioned spec would be global.
    return delete['seq'] > data['seq'] and (delete['unpartitioned'] or same_scope(delete, data))


def eq_matches(key, deleted_keys):
    return key in deleted_keys   # (None,) matches (None,): null equals null


def column(field, by_id, n):
    """Project by field id: a field the file does not have reads as null."""
    return by_id.get(field['id'], [None] * n)


def main():
    chain = committed_chain()
    meta, snap, schema = resolve_as_of(chain)
    files = scan(snap, chain)
    mapping = name_mapping(meta)
    datas = [f for f in files if f['content'] == 0]
    pos = [f for f in files if f['content'] == 1]
    eqs = [f for f in files if f['content'] == 2]
    pos_rows = {id(f): read_columns(f['local'], mapping)[0] for f in pos}
    eq_rows = {}
    for f in eqs:
        cols, n = read_columns(f['local'], mapping)
        eq_rows[id(f)] = {tuple(cols[fid][i] for fid in f['equality_ids']) for i in range(n)}

    out = []
    for d in datas:
        by_id, n = read_columns(d['local'], mapping)
        for fid, value in d['constants'].items():
            by_id.setdefault(fid, [value] * n)
        dead = set()
        for p in pos:
            if pos_applies(p, d):
                rows = pos_rows[id(p)]
                dead |= {pos_i for path, pos_i in zip(rows[2147483546], rows[2147483545]) if path == d['path']}
        projected = [column(f, by_id, n) for f in schema['fields']]
        for i in range(n):
            if i in dead:
                continue
            killed = False
            for q in eqs:
                if eq_applies(q, d):
                    key = tuple(by_id.get(fid, [None] * n)[i] for fid in q['equality_ids'])
                    if eq_matches(key, eq_rows[id(q)]):
                        killed = True
                        break
            if not killed:
                out.append([c[i] for c in projected])

    def fmt(v):
        if v is None:
            return ''
        if isinstance(v, datetime):
            # Hive's INT96 timestamps come back without a zone; they are UTC.
            v = v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v
            return v.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        if isinstance(v, Decimal):
            return f'{v:.2f}'
        return str(v)

    rows = sorted(([fmt(v) for v in r] for r in out), key=lambda r: (int(r[0]),) + tuple(r[1:]))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', newline='') as fh:
        w = csv.writer(fh, lineterminator='\n')
        w.writerow([f['name'] for f in schema['fields']])
        w.writerows(rows)
    print(f'snapshot {snap["snapshot-id"]} schema {schema["schema-id"]}: {len(rows)} rows', file=sys.stderr)


if __name__ == '__main__':
    main()
