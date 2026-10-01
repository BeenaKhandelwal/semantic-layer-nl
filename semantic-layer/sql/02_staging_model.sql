-- Phase 2 artifact: standardize raw SAP extracts and model to declared grain.
-- Grain declarations (enforced by tests, referenced by 05_semantic_model.yml):
--   fact_order_delivery   : one row per order_id
--   fact_production_order : one row per production_order_id

-- ========== Dimension: Process phases ==========
-- Literal VALUES table. Standard durations sum to 12 (phases 1-11 only; billing excluded).
CREATE OR REPLACE TABLE dim_process_phase AS
SELECT * FROM (VALUES
    (1, 'demand_capture', 'Demand & order capture', 'SAP SD', 'Sales order created', 'order_date', 0),
    (2, 'mrp_planning', 'Requirements planning', 'SAP PP (MRP)', 'Planned order created', 'mrp_date', 1),
    (3, 'production_release', 'Production order release', 'SAP PP', 'Production order released', 'release_date', 1),
    (4, 'material_staging', 'Material staging & issue', 'SAP MM', 'Goods issue to production order', 'material_issue_date', 1),
    (5, 'production_execution', 'Production execution', 'SAP PP', 'Operation confirmed', 'prod_confirm_date', 3),
    (6, 'quality_inspection', 'Quality inspection', 'SAP QM', 'Usage decision', 'qm_final_decision_date', 1),
    (7, 'goods_receipt', 'Goods receipt to stock', 'SAP MM / EWM', 'GR posted to unrestricted stock', 'gr_date', 1),
    (8, 'picking_packing', 'Picking & packing', 'SAP EWM', 'Picking completed', 'picking_date', 1),
    (9, 'goods_issue', 'Goods issue / dispatch', 'SAP LE-SHP', 'Actual goods issue', 'goods_issue_date', 0),
    (10, 'transportation', 'Transportation', 'SAP TM', 'Shipment dispatched', 'shipment_date', 3),
    (11, 'delivery_confirmation', 'Delivery confirmation', 'SAP TM / LE', 'POD / delivery confirmed', 'final_delivery_date', 0),
    (12, 'billing', 'Billing', 'SAP SD', 'Invoice created', 'invoice_date', 1)
) AS t(phase_seq, phase_key, phase_name, sap_module, business_event, timestamp_field, standard_duration_days);

-- ========== Staging views ==========

CREATE OR REPLACE VIEW stg_sales_orders AS
SELECT order_id, region, plant, warehouse, carrier, customer_id,
       CAST(order_date AS DATE)               AS order_date,
       CAST(promised_delivery_date AS DATE)    AS promised_delivery_date,
       CAST(NULLIF(promised_date_original,'') AS DATE) AS promised_date_original,
       order_status
FROM read_csv_auto('__DATA_DIR__/sales_orders_raw.csv', header=true, all_varchar=true);

CREATE OR REPLACE VIEW stg_deliveries AS
SELECT delivery_id, order_id, delivery_leg,
       CAST(NULLIF(picking_date,'') AS DATE)       AS picking_date,
       CAST(NULLIF(goods_issue_date,'') AS DATE)   AS goods_issue_date,
       CAST(NULLIF(delivery_date,'') AS DATE)      AS delivery_date,
       delivery_status
FROM read_csv_auto('__DATA_DIR__/deliveries_raw.csv', header=true, all_varchar=true);

-- Collapse deliveries to ORDER grain. This CTE is the whole ballgame:
-- max(delivery_date) because an order is delivered when its LAST leg lands.
CREATE OR REPLACE VIEW delivery_by_order AS
SELECT order_id,
       count(*)                                        AS delivery_count,
       max(delivery_date)                              AS final_delivery_date,
       count(CASE WHEN delivery_date IS NOT NULL THEN 1 END)  AS delivered_legs,
       min(picking_date)                               AS picking_date,
       min(goods_issue_date)                           AS goods_issue_date
FROM stg_deliveries
GROUP BY order_id;

CREATE OR REPLACE VIEW stg_production_orders AS
SELECT production_order_id, order_id, plant,
       CAST(NULLIF(mrp_date,'') AS DATE)              AS mrp_date,
       CAST(NULLIF(release_date,'') AS DATE)          AS release_date,
       CAST(NULLIF(scheduled_finish_date,'') AS DATE) AS scheduled_finish_date,
       CAST(NULLIF(material_issue_date,'') AS DATE)   AS material_issue_date,
       CAST(NULLIF(confirm_date,'') AS DATE)          AS confirm_date,
       CAST(NULLIF(gr_date,'') AS DATE)               AS gr_date,
       status
FROM read_csv_auto('__DATA_DIR__/production_orders_raw.csv', header=true, all_varchar=true);

-- Inspection lots: FIRST vs FINAL usage decision.
-- first_pass_yield_pct uses decision_seq = 1 only (rework re-inspections excluded).
CREATE OR REPLACE VIEW inspection_by_prod_order AS
SELECT production_order_id,
       min(CASE WHEN decision_seq='1' THEN CAST(decision_date AS DATE) END) AS qm_first_decision_date,
       max(CAST(decision_date AS DATE))                                     AS qm_final_decision_date,
       max(CASE WHEN decision_seq='1' THEN usage_decision END)              AS first_usage_decision,
       count(*)                                                             AS decision_count
FROM read_csv_auto('__DATA_DIR__/inspection_lots_raw.csv', header=true, all_varchar=true)
GROUP BY production_order_id;

CREATE OR REPLACE VIEW stg_shipments AS
SELECT shipment_id, delivery_id, carrier,
       CAST(NULLIF(dispatch_date,'') AS DATE)  AS dispatch_date,
       CAST(NULLIF(delivery_date,'') AS DATE)  AS delivery_date,
       delivery_status
FROM read_csv_auto('__DATA_DIR__/shipments_raw.csv', header=true, all_varchar=true);

CREATE OR REPLACE VIEW shipment_by_order AS
SELECT d.order_id,
       min(s.dispatch_date) AS shipment_date
FROM stg_deliveries d
LEFT JOIN stg_shipments s
    ON d.delivery_id = s.delivery_id
GROUP BY d.order_id;

CREATE OR REPLACE VIEW stg_goods_movements AS
SELECT movement_id, production_order_id, movement_type,
       CAST(NULLIF(posting_date,'') AS DATE) AS posting_date
FROM read_csv_auto('__DATA_DIR__/goods_movements_raw.csv', header=true, all_varchar=true);

-- ========== Order-grain fact table ==========
-- One row per order_id. LEFT JOINs throughout so make-to-stock orders (SO-1015) survive.

-- Phase standards as a single row of named columns, read from dim_process_phase so the
-- durations are declared in exactly one place. Any change there flows through the
-- variances, the attribution and the slack column together.
CREATE OR REPLACE VIEW phase_standard AS
SELECT
    max(CASE WHEN phase_key = 'mrp_planning'          THEN standard_duration_days END) AS std_mrp,
    max(CASE WHEN phase_key = 'production_release'    THEN standard_duration_days END) AS std_release,
    max(CASE WHEN phase_key = 'material_staging'      THEN standard_duration_days END) AS std_issue,
    max(CASE WHEN phase_key = 'production_execution'  THEN standard_duration_days END) AS std_confirm,
    max(CASE WHEN phase_key = 'quality_inspection'    THEN standard_duration_days END) AS std_qm,
    max(CASE WHEN phase_key = 'goods_receipt'         THEN standard_duration_days END) AS std_gr,
    max(CASE WHEN phase_key = 'picking_packing'       THEN standard_duration_days END) AS std_picking,
    max(CASE WHEN phase_key = 'goods_issue'           THEN standard_duration_days END) AS std_goods_issue,
    -- Transportation absorbs delivery_confirmation (phase 11, a 0-day POD event): the
    -- final span runs from goods issue to the confirmed delivery date, so its standard
    -- must cover both or the chain would not reconcile against std_to_delivery.
    max(CASE WHEN phase_key = 'transportation'        THEN standard_duration_days END)
      + max(CASE WHEN phase_key = 'delivery_confirmation' THEN standard_duration_days END) AS std_shipment,
    -- Slack budget: every phase up to delivery confirmation. Billing (phase 12) is
    -- excluded because it happens after delivery and cannot consume delivery slack.
    sum(CASE WHEN phase_seq <= 11 THEN standard_duration_days ELSE 0 END) AS std_to_delivery
FROM dim_process_phase;

CREATE OR REPLACE TABLE fact_order_delivery AS
WITH order_variance AS (
    -- One variance per phase, END-ANCHORED: a gap belongs to the phase it ends at.
    -- NULL when either endpoint is missing (make-to-stock, undelivered) -- a missing
    -- phase must not read as a 0-day variance, which would look like on-standard.
    SELECT
        o.order_id,
        date_diff('day', o.order_date,          p.mrp_date)             - s.std_mrp      AS var_mrp,
        date_diff('day', p.mrp_date,            p.release_date)         - s.std_release  AS var_release,
        date_diff('day', p.release_date,        p.material_issue_date)  - s.std_issue    AS var_issue,
        date_diff('day', p.material_issue_date, p.confirm_date)         - s.std_confirm  AS var_confirm,
        date_diff('day', p.confirm_date,        i.qm_final_decision_date) - s.std_qm     AS var_qm,
        date_diff('day', i.qm_final_decision_date, p.gr_date)           - s.std_gr       AS var_gr,
        date_diff('day', p.gr_date,             d.picking_date)         - s.std_picking  AS var_picking,
        date_diff('day', d.picking_date,        d.goods_issue_date)     - s.std_goods_issue AS var_goods_issue,
        -- Starts at goods issue, not at dispatch. Dispatch is where the transportation
        -- phase's own timestamp sits, but the span from goods issue to dispatch has to
        -- belong to somebody: measuring from shipment_date left that time unowned, so a
        -- dispatch hold produced no variance in any column and a late order came back
        -- with a NULL cause. See test_variance_chain_is_contiguous.
        date_diff('day', d.goods_issue_date,    d.final_delivery_date)  - s.std_shipment AS var_shipment
    FROM stg_sales_orders o
    CROSS JOIN phase_standard s
    LEFT JOIN delivery_by_order d        ON o.order_id = d.order_id
    LEFT JOIN shipment_by_order sh       ON o.order_id = sh.order_id
    LEFT JOIN stg_production_orders p    ON o.order_id = p.order_id
    LEFT JOIN inspection_by_prod_order i ON p.production_order_id = i.production_order_id
),
attribution AS (
    -- Unpivot the variances to rows, then take one argmax. Expressed once, so the
    -- standards can never drift out of step between phases the way eight parallel
    -- CASE branches would. Ordering by variance DESC, phase_seq ASC makes the tie
    -- break to the earliest phase explicit rather than incidental.
    SELECT order_id, phase_key AS delay_attribution_phase
    FROM (
        SELECT order_id, phase_key, variance_days,
               row_number() OVER (
                   PARTITION BY order_id
                   ORDER BY variance_days DESC, phase_seq ASC
               ) AS rn
        FROM (
            SELECT order_id,  2 AS phase_seq, 'mrp_planning'         AS phase_key, var_mrp      AS variance_days FROM order_variance
            UNION ALL SELECT order_id, 3,  'production_release',   var_release      FROM order_variance
            UNION ALL SELECT order_id, 4,  'material_staging',     var_issue        FROM order_variance
            UNION ALL SELECT order_id, 5,  'production_execution', var_confirm      FROM order_variance
            UNION ALL SELECT order_id, 6,  'quality_inspection',   var_qm           FROM order_variance
            UNION ALL SELECT order_id, 7,  'goods_receipt',        var_gr           FROM order_variance
            UNION ALL SELECT order_id, 8,  'picking_packing',      var_picking      FROM order_variance
            UNION ALL SELECT order_id, 9,  'goods_issue',          var_goods_issue  FROM order_variance
            UNION ALL SELECT order_id, 10, 'transportation',       var_shipment     FROM order_variance
        ) unpivoted
        -- Only a phase that ran LONGER than standard can explain a delay. This also
        -- drops NULL variances (NULL > 0 is NULL, never true), so a phase that did not
        -- run -- make-to-stock skipping production -- can never be blamed for a delay.
        -- Do not relax this to >= 0: an on-standard phase would then tie with a real
        -- overrun and, being earlier, win the tie-break.
        WHERE variance_days > 0
    ) ranked
    WHERE rn = 1
)
SELECT
    o.order_id,
    o.region,
    o.plant,
    o.warehouse,
    o.carrier,
    o.customer_id,
    o.order_date,
    o.promised_delivery_date,
    o.promised_date_original,
    o.order_status,

    -- Production order linkage
    p.production_order_id,

    -- Delivery information
    COALESCE(d.delivery_count, 0) AS delivery_count,
    d.final_delivery_date,

    -- Computed flags
    (d.final_delivery_date IS NOT NULL AND d.delivered_legs = d.delivery_count) AS is_delivered,
    (o.order_status <> 'CANC' AND o.promised_delivery_date <= DATE '__AS_OF_DATE__') AS is_eligible,
    (o.order_status <> 'CANC'
     AND o.promised_delivery_date <= DATE '__AS_OF_DATE__'
     AND d.final_delivery_date IS NOT NULL
     AND d.delivered_legs = d.delivery_count
     AND d.final_delivery_date <= o.promised_delivery_date) AS is_on_time,

    -- Delay calculation
    CASE
        WHEN d.final_delivery_date IS NOT NULL
        THEN date_diff('day', o.promised_delivery_date, d.final_delivery_date)
        ELSE NULL
    END AS delay_days,

    -- Phase timestamps
    p.mrp_date,
    p.release_date,
    p.scheduled_finish_date,
    p.material_issue_date,
    p.confirm_date AS prod_confirm_date,
    i.qm_first_decision_date,
    i.qm_final_decision_date,
    p.gr_date,
    d.picking_date,
    d.goods_issue_date,
    sh.shipment_date,
    -- Billing (phase 12). MODELED, not measured: no raw extract carries a billing
    -- document (goods_movements_raw has only 261 issue and 101 GR movements), so this
    -- is final_delivery_date plus the standard billing duration read from
    -- dim_process_phase -- never a second hardcoded constant. Cast to DATE to match
    -- every other phase column; an INTERVAL add would silently yield TIMESTAMP.
    -- Downstream note: the DQ timeliness rule reads max(invoice_date), so it measures
    -- how current the *delivery* data is, not true billing latency.
    CASE WHEN d.final_delivery_date IS NOT NULL
         THEN CAST(d.final_delivery_date + bill.standard_duration_days AS DATE)
         ELSE NULL
    END AS invoice_date,

    -- Phase variances (actual - standard), in days.
    -- END-ANCHORED: each gap is owned by the phase it ENDS at, so every phase has
    -- exactly one owner and the standards below sum to 12 -- the same 12 subtracted
    -- by available_slack_days. Standards come from dim_process_phase (phases 2-11;
    -- demand_capture and delivery_confirmation are 0-day events, billing is post-delivery).
    v.var_mrp,
    v.var_release,
    v.var_issue,
    v.var_confirm,
    v.var_qm,
    v.var_gr,
    v.var_picking,
    v.var_goods_issue,
    v.var_shipment,

    -- Largest positive variance names the phase that caused the delay. Populated only
    -- for late, delivered, eligible orders -- NULL otherwise, because an order that was
    -- on time or is not yet due has no delay to explain. Derived purely from event
    -- dates; the seed CSV's expected_attribution_phase oracle column is never read
    -- here, so test_attribution_matches_oracle is a real check rather than a mirror.
    CASE WHEN o.order_status <> 'CANC'
              AND o.promised_delivery_date <= DATE '__AS_OF_DATE__'
              AND d.final_delivery_date IS NOT NULL
              AND d.delivered_legs = d.delivery_count
              AND d.final_delivery_date > o.promised_delivery_date
         THEN a.delay_attribution_phase
         ELSE NULL
    END AS delay_attribution_phase,

    -- Slack the promise allowed beyond the standard process duration. Negative means
    -- the order was promised faster than the process can run even with zero variance.
    date_diff('day', o.order_date, o.promised_delivery_date) - s.std_to_delivery
        AS available_slack_days

FROM stg_sales_orders o
CROSS JOIN phase_standard s
LEFT JOIN delivery_by_order d
    ON o.order_id = d.order_id
LEFT JOIN shipment_by_order sh
    ON o.order_id = sh.order_id
LEFT JOIN stg_production_orders p
    ON o.order_id = p.order_id
LEFT JOIN inspection_by_prod_order i
    ON p.production_order_id = i.production_order_id
LEFT JOIN order_variance v
    ON o.order_id = v.order_id
LEFT JOIN attribution a
    ON o.order_id = a.order_id
CROSS JOIN (SELECT standard_duration_days FROM dim_process_phase WHERE phase_key = 'billing') bill;

-- ========== Production order fact table ==========

CREATE OR REPLACE TABLE fact_production_order AS
SELECT
    p.production_order_id,
    p.order_id,
    p.plant,
    p.mrp_date,
    p.release_date,
    p.scheduled_finish_date,
    p.material_issue_date,
    p.confirm_date,
    p.gr_date,
    p.status,
    i.qm_first_decision_date,
    i.qm_final_decision_date,
    i.first_usage_decision,
    i.decision_count,
    (p.confirm_date IS NOT NULL
     AND p.scheduled_finish_date IS NOT NULL
     AND p.confirm_date <= p.scheduled_finish_date) AS is_on_schedule
FROM stg_production_orders p
LEFT JOIN inspection_by_prod_order i
    ON p.production_order_id = i.production_order_id;
