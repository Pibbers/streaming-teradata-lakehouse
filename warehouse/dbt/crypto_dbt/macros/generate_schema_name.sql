{#
  Override the default dbt schema-naming behaviour.

  By default dbt prefixes the target schema onto custom schemas
  (e.g. "crypto_db_stg").  In Teradata, schemas ARE databases, so we
  want each custom schema to map directly to a Teradata database:
    - staging models   → Teradata database  stg
    - mart models      → Teradata database  marts
    - no custom schema → target.schema from profiles.yml
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
