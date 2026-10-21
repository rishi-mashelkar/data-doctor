-- A ref that resolves when the var is on, and a missing one when it is off.
{% if var('fixed', true) %}
select order_id, amount from {{ ref('stg_orders') }}
{% else %}
select order_id, amount from {{ ref('stg_orders_missing') }}
{% endif %}
