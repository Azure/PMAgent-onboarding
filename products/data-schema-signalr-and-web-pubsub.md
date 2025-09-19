# SignalR and Web PubSub - Product and Data Overview Template

## 1. Product Overview

SignalR and Web PubSub is an Azure real-time messaging product family that includes Azure SignalR Service (ASRS), Azure Web PubSub (AWPS), and Web PubSub for Socket.IO. This onboarding provides the canonical Kusto Query Playbook and data model assumptions used for OKR/ARR tracking, customer growth (including AI cohort), usage and revenue analysis, service type growth, feature adoption (e.g., replicas, autoscale, Blazor Server), external/billable/top customer insights, QoS, and related business and operational metrics.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**:
  SignalR and Web PubSub
- **Product Nick Names**: 
  **[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations. Examples might include: "SignalR", "ASRS", "Web PubSub", "AWPS", "SocketIO".
- **Kusto Cluster**:
  signalrinsights.eastus2
- **Kusto Database**:
  SignalRBI
- **Access Control**:
  **[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed groups/users here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

# SignalR and Web PubSub — Kusto Query Playbook

## Overview
Product: SignalR and Web PubSub

Summary: Power BI Power Query M blocks querying Azure Data Explorer for business analysis of SignalR and Web PubSub. Queries target cluster signalrinsights.eastus2, database SignalRBI, covering OKR/ARR and AI customer growth, usage and revenue, service type growth, feature tracking, external/billable/top customers, QoS, VS integration, runtime requests, retention, categories, and related metrics.

Primary Cluster and Database:
- Cluster: signalrinsights.eastus2
- Database: SignalRBI
- Alternates referenced by queries:
  - armprodgbl.eastus (ARM telemetry: Requests, HttpIncomingRequests)
  - ddtelinsights (VS/WebTools client telemetry: WebTools_Raw)

User emphasis:
- High priority: OKR analysis; ARR/AI customer growth; usage and revenue; service type growth (SignalR/Web PubSub/Web PubSub for SocketIO); feature tracking (replicas, autoscale, blazor-server, etc.); external/billable/top customers.
- Low priority: VS integration; QoS analysis; RuntimeRequests.


## Conventions & Assumptions

### Time semantics
- Observed timestamp columns:
  - Date (daily facts: BillingUsage_Daily, ResourceMetrics, FeatureTrack*, …)
  - env_time (QoS tables OperationQoS_Daily, ConnectivityQoS_Daily)
  - AdvancedServerTimestampUtc (WebTools_Raw)
  - TIMESTAMP (ARM telemetry)
- Canonical Time Column: Date
  - Alias others as needed:
    - project-rename Date = env_time
    - project-rename Date = AdvancedServerTimestampUtc
    - project-rename Date = TIMESTAMP
- Typical windows and rollups:
  - Short windows: 28–60 days with ago(28d)/ago(60d)
  - Weekly: startofweek(Date)
  - Monthly: startofmonth(Date), month-end alignment via startofday(endofmonth(Date))
- Timezone: unknown. Assume UTC. Avoid including current day since many queries explicitly exclude it via completeness gates.

### Freshness & Completeness Gates
- Daily ingestion; current-day data may be incomplete.
- Regional completeness gate (multi-slice): choose the last date where both regions report data to avoid partials.
  - Sentinel regions used: 'australiaeast' and 'westeurope'
- Recommended effective end times:
  - Daily: gate to last common regional date
  - Weekly/Monthly: use startofweek/startofmonth on a gated current

Pattern (compute effective end date across regions):
```kusto
let EndDate =
    toscalar(
        BillingUsage_Daily
        | where Date > ago(10d) and Region in ('australiaeast', 'westeurope')
        | summarize RegionsSeen = dcount(Region) by Date
        | where RegionsSeen >= 2
        | top 1 by Date desc
        | project Date
    );
```

### Joins & Alignment
- Frequent keys:
  - ResourceId (ARM resource path)
  - Date (daily alignment)
  - SubscriptionId (tenant dimension joins)
  - Region (in facts, QoS)
- Typical join kinds:
  - inner for alignment with activity (e.g., MaxConnectionCount_Daily or ResourceMetrics)
  - leftouter to bring in dimensions (SubscriptionMappings, RPSettingLatest)
  - fullouter to combine actuals with goal datatables for OKRs
- Post-join hygiene:
  - Normalize IDs: tolower(ResourceId), coalesce/overwrite TimeStamp after fullouter goal joins
  - Remove duplicate columns: project-away
  - Replica normalization: strip '/replicas/' suffix for primary resource identity

### Filters & Idioms
- Service provider filters:
  - SignalR: ResourceId has 'microsoft.signalrservice/signalr'
  - Web PubSub: ResourceId has 'microsoft.signalrservice/webpubsub'
- Exclude internal usage:
  - SubscriptionId !in (SignalRTeamInternalSubscriptionIds) or SignalRTeamInternalSubscriptionIds()
- SKU rules:
  - Exclude 'MessageCount'/'MessageCountPremium' in paid revenue/consumption
  - Paid tiers of interest: 'Standard', 'Premium' (and sometimes 'Free' for population)
- Cohorts:
  - AI cohort allowlist via ResourceId: has 'gpt'/'ai'/'ml'/'cognitive' or contains 'openai'/'chatgpt'
- Counting performance:
  - Use HyperLogLog precision in distinct counts: dcount(Key, 3|4)

### Cross-cluster/DB & Sharding
- Qualifying sources:
  - Use cluster('<name>').database('<db>').<table> when needed; queries often rely on functions (e.g., Unionizer) for ARM telemetry
- Sharding by geo:
  - EU-only shards: FeatureTrackV2_EU_Daily, RuntimeRequestsGroups_EU_Daily, RuntimeTransport_EU_Daily
  - Pattern: union → normalize time and keys → summarize
- Cross-source ARM RP:
  - Union Requests and HttpIncomingRequests (ARM telemetry) and normalize fields (e.g., extract ResourceId from targetUri)

### Table classes
- Fact (daily/events): BillingUsage_Daily, ResourceMetrics, FeatureTrack*, QoS tables, ConnectionMode_Daily
  - Use for ground-truth counts and joins
- Snapshot (latest state): RPSettingLatest; retention snapshots; Cached_* snapshots (OKRs, flows)
  - Use for point-in-time state or precomputed trendlines
- Pre-aggregated: Cached_* (OKRs, TopSubscriptions, Totals)
  - Use for dashboards; prefer facts for bespoke analysis


## Entity & Counting Rules (Core Definitions)

- Entity model:
  - Resource (ResourceId) → Subscription (SubscriptionId) → Customer (CloudCustomerGuid)
  - Service classification: SignalR vs WebPubSub vs SocketIO (RPSettingLatest.Kind)
  - Grouping levels:
    - Resource-level when measuring HasConnection, LiveRatio, feature usage
    - Subscription-level for billable/cohort counts and top customers
    - Customer-level (CloudCustomerGuid) for customer totals and retention
- Counting rules:
  - Distinct counting: use dcount(Key, 3|4) to balance accuracy/performance
  - Active resource definition: HasConnection = max(MaxConnectionCount) > 0 (from ResourceMetrics)
  - Paid units: sum Quantity for SKU in ('Standard','Premium')
  - Revenue: sum Quantity * <UnitPriceBySKU>
    - Replace hardcoded constants in queries (e.g., 1.61/2.0) with placeholders in new queries:
      - Standard: <UnitPriceStandard>
      - Premium: <UnitPricePremium>
  - Cohorts:
    - External vs Internal: derive via SubscriptionMappings.CustomerType
    - AI cohort: ResourceId keyword allowlist (gpt/ai/ml/cognitive/openai/chatgpt)
- When to apply:
  - Exclude internal subs by default for business metrics
  - Gate time to last complete day and align weeks/months for rollups
  - Remove '/replicas/' suffix to consolidate resource identities where applicable


## Canonical Tables
Product: SignalR and Web PubSub
Primary ADX: cluster("signalrinsights.eastus2").database("SignalRBI")
Timezone: unknown. Many queries use startofweek/startofmonth/ago windows; be careful with current day partial data.
Common assumptions and patterns:
- Tenant/Provider filters:
  - ResourceId has 'microsoft.signalrservice/signalr' for SignalR
  - ResourceId has 'microsoft.signalrservice/webpubsub' for Web PubSub and Web PubSub for Socket.IO
- Exclude internal usage: SubscriptionId !in (SignalRTeamInternalSubscriptionIds) — typically a function that returns internal subscription list
- Normalize time:
  - Day-level facts use Date or env_time
  - Weekly aggregates use startofweek(Date) and monthly aggregates use startofmonth(Date)
  - Snapshots align to end-of-week/month via startofday(endofmonth(Date)) in joins
- SKU filtering:
  - Paid consumption excludes 'MessageCount'/'MessageCountPremium' in many revenue/usage queries
- Joins:
  - SubscriptionMappings is the canonical dimension for CustomerType, BillingType, SegmentName, and tenant-level identities
  - ResourceMetrics provides connection/message counters keyed by Date and ResourceId
  - RPSettingLatest enriches with Kind (WebPubSub vs SocketIO) and ServiceMode/Extras

Order: High priority first, then Normal, then Low.

---

### Table: BillingUsage_Daily (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- What this table represents: Daily billing/usage fact by resource/subscription/SKU. Zero rows for a day implies no usage recorded for that resource/subscription/SKU.
- Freshness expectations: Daily ingestion; many queries use last 30–60 days, often constrained by latest common date across regions. Avoid current-day partials.
- When to use / When to avoid:
  - Use for revenue estimation, paid units, usage segmentation by SKU, service type, region.
  - Use to detect active subscriptions/resources (joins with ResourceMetrics or MaxConnectionCount_Daily to confirm activity).
  - Avoid counting MessageCount SKUs for revenue unless explicitly needed (frequently excluded).
  - Avoid without excluding internal subscriptions when doing external business metrics.
- Similar tables & how to choose:
  - ResourceMetrics: use for connection/message counters; join with BillingUsage_Daily for richer KPIs.
  - Cached_* snapshot tables: use for pre-aggregated OKR trendlines; BillingUsage_Daily is raw fact.
- Common Filters:
  - Date >= ago(Nd), Date between specific startofweek/month windows
  - ResourceId has '/signalr/' or '/webpubsub/'
  - SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
  - SKU in ('Free','Standard','Premium') and SKU !in ('MessageCount','MessageCountPremium') for paid analysis
- Table columns:
  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | Date          | datetime | Usage day (UTC). Use startofweek/startofmonth(Date) to aggregate. |
  | SubscriptionId| string   | Azure subscription GUID. Join to SubscriptionMappings. |
  | ResourceId    | string   | ARM resource ID; filter by provider path for service type. |
  | SKU           | string   | Pricing tier: Free/Standard/Premium/MessageCount/MessageCountPremium. |
  | Quantity      | real     | Units for billing computations; often multiplied by unit prices. |
  | Region        | string   | Azure region of usage. |
- Column Explain:
  - Date: drive time windows and slicers. Use startofweek/month for cohorting.
  - SKU: filter for paid vs. free vs. counters; derive revenue tiers.
  - ResourceId: provider filter for SignalR/WebPubSub; split to get SubscriptionId.
  - SubscriptionId: join to SubscriptionMappings for CustomerType/BillingType/SegmentName.
  - Quantity: convert to Income/Revenue using tier-specific unit prices.

---

### Table: ResourceMetrics (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- What this table represents: Daily runtime metrics per resource (connections/messages/averages). Zero rows imply missing telemetry for that day/resource.
- Freshness expectations: Daily; many queries align ResourceMetrics with BillingUsage_Daily on Date and ResourceId.
- When to use / When to avoid:
  - Use to compute MaxConnectionCount, SumMessageCount, AvgConnectionCount by resource, then aggregate by week/month.
  - Use to detect “HasConnection” activity (MaxConnectionCount > 0).
  - Avoid standalone tenant analytics; join with SubscriptionMappings for CustomerType or with RPSettingLatest for service settings.
- Similar tables & how to choose:
  - FeatureTrack_* for feature usage; ResourceMetrics for core runtime load indicators.
  - ConnectionMode_Daily specifically for connection mode split; ResourceMetrics for totals.
- Common Filters:
  - Date windows (ago(61d), startofweek/month)
  - ResourceId contains provider path; sometimes trimmed to primary resource when replicas are present
- Table columns:
  | Column            | Type     | Description or meaning |
  |-------------------|----------|------------------------|
  | Date              | datetime | Metric date (UTC). |
  | ResourceId        | string   | ARM resource ID; sometimes normalized to remove '/replicas/'. |
  | MaxConnectionCount| long     | Peak concurrent connections per day. |
  | SumMessageCount   | long     | Total messages per day. |
  | AvgConnectionCount| long     | Daily average connections. |
  | Region            | string   | Azure region of the resource. |
- Column Explain:
  - MaxConnectionCount: key signal for “active” definitions and top subscriptions.
  - SumMessageCount: volume metric for usage intensity.
  - ResourceId + Date: primary join keys to BillingUsage_Daily and RPSettingLatest.

---

### Table: SubscriptionMappings (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- What this table represents: Subscription dimension and segmentation attributes.
- Freshness expectations: As upstream CRM/billing syncs; treat as slowly changing dimension.
- When to use / When to avoid:
  - Use to derive CustomerType (Internal/External), BillingType, SegmentName, Offer fields.
  - Use in top customers enrichment and cohort breakdowns.
  - Avoid assuming direct revenue columns here—join to BillingUsage_Daily for amounts.
- Similar tables & how to choose:
  - CustomerModel for richer commercial KPIs; SubscriptionMappings for “who/segment”.
- Common Filters:
  - Join on SubscriptionId; most queries left-join to keep fact row coverage.
- Table columns:
  | Column          | Type   | Description |
  |-----------------|--------|-------------|
  | SubscriptionId  | string | Subscription GUID; join key. |
  | CustomerType    | string | 'Internal' or 'External' (often controlling UsageType). |
  | BillingType     | string | Commercial classification (e.g., EA/PAYG). |
  | SegmentName     | string | Business segment name. |
  | CloudCustomerGuid| string| Tenant/customer id for customer-level counts. |
- Column Explain:
  - CustomerType controls ‘UsageType’ derivation in queries.
  - SegmentName is widely used in free/standard/premium splits by segment.

---

### Table: RPSettingLatest (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- What this table represents: Latest resource-plane settings snapshot per resource (e.g., ServiceMode, Extras JSON, Kind).
- Freshness expectations: Snapshot; expect delayed refresh vs. runtime metrics.
- When to use / When to avoid:
  - Use to enrich resources with ServiceMode and Kind (e.g., SocketIO).
  - Use to detect features via Extras, e.g., 'isAspire', or socketIO.serviceMode.
  - Avoid as a usage source; it’s configuration metadata.
- Similar tables & how to choose:
  - FeatureTrack_* for observed feature usage; RPSettingLatest for configured capability/state.
- Common Filters:
  - Join on ResourceId; normalize case; sometimes remove '/replicas' suffix in ResourceId.
- Table columns:
  | Column     | Type    | Description |
  |------------|---------|-------------|
  | ResourceId | string  | ARM ID; join key to facts. |
  | ServiceMode| string  | Service mode label (e.g., Default/Serverless/Server). |
  | Kind       | string  | Product kind (WebPubSub vs SocketIO). |
  | Extras     | dynamic | JSON bag with additional flags (e.g., isAspire, socketIO.serviceMode). |
- Column Explain:
  - Kind: used to bucket WebPubSub vs. SocketIO aggregations.
  - Extras: parsed with extract_json to derive detailed flags.

---

### Table: FeatureTrack_Daily (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- What this table represents: Daily feature usage tracking (event-style) by Feature/Category/ResourceId.
- Freshness expectations: Daily; can be used in rolling weekly windows.
- When to use / When to avoid:
  - Use to quantify adoption of features (e.g., ServerSticky, NeededScale).
  - Use to enrich top subscriptions with behavioral flags.
  - Avoid for load metrics; use ResourceMetrics instead.
- Similar tables & how to choose:
  - FeatureTrackV2_* for newer/normalized categories; use V2 where available.
- Common Filters:
  - Date > startofweek(now()) - N days
  - ResourceId contains service provider path
  - Exclude internal subscription ids
- Table columns:
  | Column       | Type     | Description |
  |--------------|----------|-------------|
  | Date         | datetime | Event date (UTC). |
  | Feature      | string   | Feature name (e.g., ServerSticky). |
  | Category     | string   | Feature category. |
  | RequestCount | long     | Count of tracked requests/occurrences. |
  | ResourceId   | string   | ARM resource. Split to get SubscriptionId if needed. |
- Column Explain:
  - Feature/Category: group keys to count adoption.
  - RequestCount: volume indicator; often used as >0 boolean adoption.

---

### Table: FeatureTrackV2_Daily (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- What this table represents: Updated/normalized feature tracking with refined categories (V2).
- Freshness expectations: Daily; used in last 56 days windows.
- When to use / When to avoid:
  - Use for SignalR feature adoption by week; normalized categories via string transforms in queries.
  - Avoid mixing V1 and V2 without harmonizing Categories.
- Similar tables & how to choose:
  - FeatureTrackV2_EU_Daily for EU-silo; union both for full coverage.
- Common Filters:
  - Date > startofweek(now()) - 56d
  - ResourceId has '/signalr/' or '/webpubsub/'
- Table columns:
  | Column       | Type     | Description |
  |--------------|----------|-------------|
  | Date         | datetime | Event date. |
  | Feature      | string   | Feature name. |
  | Category     | string   | Often normalized in query. |
  | RequestCount | long     | Volume. |
  | ResourceId   | string   | ARM resource. |
  | Properties   | dynamic  | Dropped in queries; raw metadata. |
- Column Explain:
  - Category: often re-labeled in query (e.g., Ping groups).
  - Properties: not used downstream; filtered away.

---

### Table: FeatureTrackV2_EU_Daily (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- What this table represents: EU-silo V2 feature tracking.
- Freshness expectations: Daily; union with global V2 for full picture.
- When to use: Combine with FeatureTrackV2_Daily to avoid geo gaps.
- Similar tables: FeatureTrackV2_Daily (global).
- Common Filters: Same as V2.
- Table columns: Same as FeatureTrackV2_Daily.
- Column Explain: Same as FeatureTrackV2_Daily.

---

### Table: FeatureTrack_AutoScale_Daily (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- What this table represents: Daily detection of autoscale-related signals per resource.
- Freshness expectations: Daily; used for percentage of Premium with autoscale signals.
- When to use:
  - Weekly percentage of premium resources with autoscale features.
- Similar tables: FeatureTrack_* for broader feature usage.
- Common Filters:
  - Date >= startofweek(now(), -12)
  - SKU == 'Premium' in BillingUsage_Daily for denominator
- Table columns:
  | Column     | Type     | Description |
  |------------|----------|-------------|
  | Date       | datetime | Day. |
  | ResourceId | string   | ARM resource id. |
- Column Explain:
  - ResourceId: dcount to get resource counts; join with BillingUsage_Daily for premium total.

---

### Table: Cached_TopSubscriptions_Snapshot (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- What this table represents: Snapshot of top subscriptions with per-subscription summary KPIs and retention flags.
- Freshness expectations: Snapshot refreshed periodically; queries use last ~29 days for enrichment.
- When to use:
  - Top customers: KPI drill-down with ResourceMetrics and BillingUsage_Daily.
  - Customer success signals (retained/new flags).
- Similar tables: CustomerModel for commercial attributes.
- Common Filters:
  - Service == 'SignalR' or 'WebPubSub'
  - Join on SubscriptionId to enrich with metrics and tags/features/modes.
- Table columns:
  | Column         | Type    | Description |
  |----------------|---------|-------------|
  | Service        | string  | Service filter: SignalR or WebPubSub. |
  | SubscriptionId | string  | Subscription GUID. |
  | StartDate      | datetime| First active date window. |
  | EndDate        | datetime| Last active date window. |
  | Revenue        | real    | Revenue estimate for ranking (when present). |
  | MaxConnection  | long    | Max connections (when present). |
  | MessageCount   | long    | Messages (when present). |
- Column Explain:
  - StartDate/EndDate drive IsNew/IsRetained flags in queries.
  - SubscriptionId used to join to runtime and billing facts.

---

### Table: CustomerModel (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- What this table represents: Customer-level attributes per subscription with revenue and performance KPIs.
- Freshness expectations: Periodic; do not assume daily refresh.
- When to use:
  - Enrich top-subscriptions output: Revenue, MaxConnection, MessageCount, Rate, names/offer info.
- Similar tables: SubscriptionMappings for additional segmentation; CustomerModel has more KPIs.
- Common Filters: Join on SubscriptionId.
- Table columns:
  | Column           | Type   | Description |
  |------------------|--------|-------------|
  | SubscriptionId   | string | Join key. |
  | Revenue          | real   | Revenue KPI. |
  | MaxConnection    | long   | Peak connections KPI. |
  | MessageCount     | long   | Messages KPI. |
  | Rate             | real   | Rate/score metric. |
  | CloudCustomerName| string | Display name. |
  | TPName           | string | Partner/TP name if any. |
  | BillingType      | string | Billing classification. |
  | OfferName/Type   | string | Offer metadata. |
  | P360_ID/TPID     | string | CRM/customer ids for deep links. |
- Column Explain:
  - Revenue/MaxConnection/MessageCount: used directly for top ranking and display.

---

### Table: OKRv2021 (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- What this table represents: Historical OKR time series keyed by Date, Category, Value.
- Freshness expectations: Historical; updated as targets/metrics evolve.
- When to use:
  - Pivot by Category to create multi-metric OKR dashboards.
- Similar tables: OKRv2021_AWPS, OKRv2021_SocketIO for service/variant splits.
- Common Filters:
  - Date >= datetime(20200701)
- Table columns:
  | Column  | Type     | Description |
  |---------|----------|-------------|
  | Date    | datetime | Month-end or tracked date. |
  | Category| string   | Metric category key. |
  | Value   | real     | Numeric value. |
- Column Explain:
  - Category/Value used with evaluate pivot for dashboard-shape output.

---

### Table: OKRv2021_AWPS (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- Represents: OKR time series for Web PubSub (AWPS).
- Freshness: Historical.
- Use: Same as OKRv2021; union with SocketIO variant in combined reports.
- Columns: Date, Category, Value (same usage).
- Explain: Same pivoting behavior.

---

### Table: OKRv2021_SocketIO (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- Represents: OKR time series for SocketIO.
- Freshness & Use: As above.

---

### Table: OKR_AWPS_SocketIO (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- What this table represents: Combined OKR measures for AWPS and SocketIO by Date, CustomerType; used with inline goals (datatable) in queries.
- Freshness expectations: Historical; used for comparison vs. target curves.
- When to use:
  - Compare actual vs. SocketIO goal/growth targets (full-outer join).
- Common Filters:
  - Date >= datetime(20230820)
- Table columns:
  | Column       | Type     | Description |
  |--------------|----------|-------------|
  | Date         | datetime | Time axis. |
  | CustomerType | string   | External/Internal. |
  | Value/Category (if present) | mixed | Metric series. |
- Column Explain:
  - Date/CustomerType: join keys against goals.

---

### Table: Cached_ZnOKRARR_Snapshot (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- What this table represents: Pre-aggregated ARR OKR snapshot by TimeStamp (Zone-level).
- Freshness expectations: Snapshot (monthly); joined with goal curves via TimeStamp.
- When to use:
  - OKR ARR tracking against targets; monthly timeline.
- Similar tables & how to choose:
  - Cached_DtOKRARR_Snapshot for ‘Dt’ variant; pick table based on dashboard.
- Common Filters:
  - Join on TimeStamp; optionally restrict to last N months.
- Table columns:
  | Column    | Type     | Description |
  |-----------|----------|-------------|
  | TimeStamp | datetime | Month-end aligned timestamp. |
  | Metrics…  | real     | Pre-aggregated ARR metrics (fields vary). |
- Column Explain:
  - TimeStamp: used as sole join alignment with goal datatable.

---

### Table: Cached_ZnOKREstRevenueWeekly_Snapshot (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- Represents: Weekly estimated revenue OKR snapshot (Zn variant).
- Freshness: Weekly snapshot.
- Use: Trendline without recomputing from raw usage.
- Columns:
  | Column    | Type     | Description |
  |-----------|----------|-------------|
  | TimeStamp | datetime | Week-aligned timestamp. |
  | Metrics…  | real     | Estimated revenue aggregates. |

---

### Table: Cached_ZnOKREstRevenueMonthly_Snapshot (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- Represents: Monthly estimated revenue OKR snapshot (Zn variant).
- Columns: TimeStamp, metric fields.

---

### Table: Cached_ZnOKRSubs_Snapshot (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- Represents: Monthly subscriber OKR snapshot (Zn).
- Use: Compare against inline WebPubSubGoal/WebPubSubGrowthGoal by TimeStamp.
- Columns: TimeStamp, metric fields.

---

### Table: Cached_CuOKRConsumption_Snapshot (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- Represents: Consumption OKR snapshot (cumulative) by TimeStamp with series for Total/SignalR/WebPubSub.
- Use: OKR consumption vs. target series.
- Columns: TimeStamp, series metrics.

---

### Table: Cached_CuOKRConsumptionWeekly_Snapshot (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- Represents: Weekly consumption snapshot (cumulative).
- Columns: TimeStamp, series metrics.

---

### Table: Cached_CuOKRConsumptionMonthly_Snapshot (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- Represents: Monthly consumption snapshot (cumulative).
- Columns: TimeStamp, series metrics.

---

### Table: Cached_DtOKRARR_Snapshot (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- Represents: OKR ARR snapshot (Dt variant) monthly.
- Use: Join to inline TotalGoal/TotalGrowthGoal by TimeStamp; filter to last ~35 months.
- Columns: TimeStamp, metrics.

---

### Table: Cached_DtOKREstRevenueWeekly_Snapshot (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- Represents: Weekly estimated revenue snapshot (Dt variant).
- Columns: TimeStamp, metrics.

---

### Table: Cached_DtOKREstRevenueMonthly_Snapshot (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- Represents: Monthly estimated revenue snapshot (Dt variant).
- Columns: TimeStamp, metrics.

---

### Table: Cached_DtOKRSubsWeekly_Snapshot (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- Represents: Weekly subscriptions snapshot (Dt variant).
- Columns: TimeStamp, metrics.

---

### Table: Cached_DtOKRSubsMonthly_Snapshot (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: High
- Represents: Monthly subscriptions snapshot (Dt variant).
- Columns: TimeStamp, metrics.

---

## Normal Priority Tables

### Table: ManageResourceTags (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Normal
- Represents: Management-plane operations with tag details and counts.
- Use: Operation volume by RequestName/Tags, resource/subscription; enrich with SubscriptionMappings.
- Common Filters: Date > ago(30d); exclude Microsoft.Authorization; RequestName != 'Other'.
- Columns:
  | Column        | Type   | Description |
  |---------------|--------|-------------|
  | Date          | datetime | Operation day. |
  | RequestName   | string | Operation name. |
  | Tags          | string | Used as RequestMethod in queries. |
  | SubscriptionId| string | Join to dimensions. |
  | ResourceId    | string | ARM resource. |
  | Count         | long   | Operation count. |

---

### Table: ConnectionMode_Daily (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Normal
- Represents: Daily connection mode counts by resource (server/serverless).
- Use: Aggregate resource and connection counts by ServiceMode per day.
- Filters: Date > ago(60d); ResourceId has '/signalr/'.
- Columns:
  | Column             | Type     | Description |
  |--------------------|----------|-------------|
  | Date               | datetime | Day. |
  | ResourceId         | string   | ARM resource. |
  | ServiceMode        | string   | Mode label. |
  | ServerlessConnection| long    | Count of serverless connections. |
  | ProxyConnection    | long     | Count of server mode connections. |

---

### Table: KPIv2019 (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Normal
- Represents: Legacy KPI time series (SignalR).
- Use: Historical KPI trend since 2019-01-01.
- Columns: Date, KPI category/value fields (pivot or filter as needed).

---

### Table: ChurnCustomers_Monthly (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Normal
- Represents: Monthly churn metrics per service with latest run per month.
- Use: Compute churn rates, Standard churn counts.
- Filters: ServiceType in ('SignalR','WebPubSub'); latest row per Month by RunDay.
- Columns:
  | Column          | Type     | Description |
  |-----------------|----------|-------------|
  | Month           | datetime | Month key. |
  | RunDay          | datetime | Snapshot run timestamp. |
  | ServiceType     | string   | Product. |
  | Standard        | long     | Standard base. |
  | StandardChurn   | long     | Standard churners. |
  | Churn           | long     | Total churners. |
  | Total           | long     | Total base. |

---

### Table: ConvertCustomer_Weekly (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Normal
- Represents: Weekly conversion funnel metrics by service.
- Use: Free→Standard/Premium, Standard→Premium transitions; latest per week.
- Columns:
  | Column             | Type     | Description |
  |--------------------|----------|-------------|
  | Week               | datetime | Week key. |
  | ServiceType        | string   | Product. |
  | RunDay             | datetime | Snapshot run. |
  | FreeToPaid         | long     | Derived in query (fallback to FreeToStandard). |
  | FreeToStandard     | long     | Count. |
  | FreeToPremium      | long     | Count. |
  | StandardToPremium  | long     | Count. |

---

### Table: RuntimeResourceTags_Daily (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Normal
- Represents: Daily runtime tags per subscription: IsAppService/IsProxy/IsStaticApps flags.
- Use: Enrich top subscriptions with runtime hosting characteristics.
- Columns:
  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Date          | datetime | Day. |
  | ServiceType   | string   | SignalR/WebPubSub. |
  | SubscriptionId| string   | Join key. |
  | IsAppService  | bool     | App Service detection. |
  | IsProxy       | bool     | Proxy usage. |
  | IsStaticApps  | bool     | Static Apps detection. |

---

### Table: DeleteSurvey (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Normal
- Represents: Deletion survey feedback for SignalR.
- Columns: TIMESTAMP, Deployment, resourceId, reason, feedback.

---

### Table: FeedbackSurvey (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Normal
- Represents: General feedback survey.
- Columns: TimeStamp, CESValue, CVAValue, Comments.

---

### Table: Cached_ResourceFlow_Snapshot (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Normal
- Represents: Weekly/Monthly resource flow snapshots by service.
- Use: Slice by Partition ('Week'/'Month'), then rename Date→Week/Month.
- Columns: Date, ServiceType, Partition, flow metrics.

---

### Table: Cached_SubsTotalWeekly_Snapshot (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Normal
- Represents: Weekly subscription totals snapshot with joins to segmentation.
- Use: dcount SubscriptionId across facets for SignalR and WebPubSub.
- Columns: Week, SubscriptionId, Region, OfferType/Name, BillingType, SKU, CustomerType, HasConnection, LiveRatio.

---

### Table: Cached_SubsTotalMonthly_Snapshot (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Normal
- Represents: Monthly subscription totals snapshot.
- Columns similar to weekly; Month key.

---

### Table: KPI_AWPS (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Normal
- Represents: Web PubSub KPI table.
- Use: AWPS-specific KPI tracking.
- Columns: Date + KPI fields (per consumer queries).

---

### Table: DeleteSurveyWebPubSub (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Normal
- Represents: Deletion survey feedback for Web PubSub.
- Columns: TIMESTAMP, Deployment, resourceId, reason, feedback.

---

### Table: ResourceFlow_Weekly (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Normal
- Represents: Function producing weekly resource flows; parameters for start/end and service code (2 for WebPubSub).
- Use: Time-bounded weekly flow analytics.
- Columns: Week plus flow counts (produced by function).

---

### Table: ResourceFlow_Monthly (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Normal
- Represents: Function producing monthly resource flows.
- Use: Monthly cohort analytics.
- Columns: Month plus flow counts.

---

### Table: SubscriptionFlow_Weekly (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Normal
- Represents: Weekly subscription flow function output.
- Columns: Week plus flow counts.

---

### Table: SubscriptionFlow_Monthly (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Normal
- Represents: Monthly subscription flow function output.
- Columns: Month plus flow counts.

---

### Table: CustomerFlow_Weekly (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Normal
- Represents: Weekly customer flow function output.
- Columns: Week plus flow counts.

---

### Table: CustomerFlow_Monthly (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Normal
- Represents: Monthly customer flow function output.
- Columns: Month plus flow counts.

---

### Table: AwpsRetention_SubscriptionSnapshot (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Normal
- Represents: Web PubSub retention snapshot for subscriptions.
- Use: Cohort retention by month/week across periods.
- Columns: StartDate, EndDate, SubscriptionId; used to compute retention Ratio.

---

### Table: AwpsRetention_CustomerSnapshot (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Normal
- Represents: Web PubSub retention snapshot for customers (C360_ID).
- Columns: StartDate, EndDate, C360_ID.

---

### Table: AwpsRetention_ResourceSnapshot (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Normal
- Represents: Web PubSub retention snapshot for resources.
- Columns: StartDate, EndDate, ResourceId.

---

### Table: KPI_SocketIO (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Normal
- Represents: Socket.IO KPI time series.
- Use: SocketIO-specific KPI dashboards.
- Columns: Date + KPI metrics.

---

## Low Priority Tables

### Table: OperationQoS_Daily (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Low
- Represents: Service operation QoS by env_time/resource/region (SignalR and WebPubSub used via provider filters).
- Use: Rolling 7/28-day QoS, weekly/monthly SlaAttainment.
- Columns:
  | Column           | Type     | Description |
  |------------------|----------|-------------|
  | env_time         | datetime | Day. |
  | resourceId       | string   | Service resource id or role. |
  | env_cloud_location| string  | Region. |
  | env_cloud_role   | string   | Role name (used as ResourceId in aggregations). |
  | totalTimeSec     | long     | Total time window. |
  | totalUpTimeSec   | long     | Up time window. |

---

### Table: ConnectivityQoS_Daily (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Low
- Represents: Connectivity QoS with same dimensions as Operation QoS.
- Columns: Same as OperationQoS_Daily.

---

### Table: ManageRPQosDaily (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Low
- Represents: RP API QoS counts by API, region, result.
- Use: QoS%, total requests; filtered API sets; rolling windows and weekly/monthly summaries.
- Columns:
  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Date          | datetime | Day. |
  | ApiName       | string   | API operation name. |
  | Region        | string   | Region. |
  | Result        | string   | Success/Timeout/CustomerError/etc. |
  | Count         | long     | Requests. |
  | CustomerType  | string   | SignalR/WebPubSub. |
  | SubscriptionId| string   | For joins. |

---

### Table: RuntimeRequestsGroups_Daily (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Low
- Represents: Daily grouped runtime request metrics by Category/Metrics for non-transport scenarios.
- Columns: Date, Category, Metrics, ResourceCount, RequestCount.

---

### Table: RuntimeRequestsGroups_EU_Daily (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Low
- Represents: EU-silo grouped runtime requests.
- Columns: Same as RuntimeRequestsGroups_Daily.

---

### Table: RuntimeTransport_Daily (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Low
- Represents: Daily transport metrics; union with EU variant; derives Metrics = Framework-Transport.
- Columns: Date, Framework, Transport, ResourceId, RequestCount.

---

### Table: RuntimeTransport_EU_Daily (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Low
- Represents: EU-silo transport metrics.
- Columns: Same as RuntimeTransport_Daily.

---

### Table: Requests (cluster("armprodgbl.eastus").database("<unknown>"))
- Priority: Low
- Represents: ARM RP ‘Requests’ telemetry (used via Unionizer).
- Use: Detect EventGrid filter operations (PUT/DELETE) over last 30 days.
- Columns: TIMESTAMP, targetResourceProvider, httpMethod, targetResourceType, targetUri, subscriptionId.

---

### Table: HttpIncomingRequests (cluster("armprodgbl.eastus").database("<unknown>"))
- Priority: Low
- Represents: Inbound RP request telemetry; used with Requests.
- Columns: Similar to Requests.

---

### Table: WebTools_Raw (cluster("ddtelinsights").database("<unknown>"))
- Priority: Low
- Represents: Visual Studio/WebTools client telemetry for SignalR awareness/provisioning.
- Use: Developer counts, ratios, provisioning SKUs/locations.
- Columns:
  | Column                     | Type    | Description |
  |----------------------------|---------|-------------|
  | AdvancedServerTimestampUtc | datetime| Event time. |
  | EventName                  | string  | Event id. |
  | Properties                 | dynamic | Payload with keys/URIs/SKUs. |
  | Measures                   | dynamic | Numeric flags for states. |
  | ExeVersion                 | string  | VS executable version. |
  | MacAddressHash             | string  | Anonymized device id. |
  | ActiveProjectId            | string  | Project id. |

---

### Table: AwpsRuntimeRequestsGroups_Daily (cluster("signalrinsights.eastus2").database("SignalRBI"))
- Priority: Low
- Represents: AWPS grouped runtime requests with metrics normalization.
- Columns: Date, Category, Metrics (normalized), counts.

---

## Views (Reusable Layers)
- None defined in source. Pre-aggregated “Cached_*” tables and Kusto functions (e.g., ResourceFlow_Weekly) act as reusable building blocks.

## Query Building Blocks (Copy-paste snippets)

- Time window template (daily with completeness gate; weekly/monthly rollups)
  - Description: Use when your daily data can be incomplete for the current day; gate to last regional-complete date, then aggregate by week/month.
  - Snippet:
```kusto
// Compute effective daily EndDate across sentinel regions
let EndDate =
    toscalar(
        BillingUsage_Daily
        | where Date > ago(10d) and Region in ('australiaeast', 'westeurope')
        | summarize RegionsSeen = dcount(Region) by Date
        | where RegionsSeen >= 2
        | top 1 by Date desc
        | project Date
    );
BillingUsage_Daily
| where Date > ago(60d) and Date <= EndDate
| summarize Total = count() by Date
| summarize ByWeek = sum(Total) by Week = startofweek(Date)
| summarize ByMonth = sum(Total) by Month = startofmonth(Date)
```

- Join template (facts + activity + dimension)
  - Description: Standard pattern to compute paid revenue/units by cohort; aligns to activity and enriches with customer meta.
  - Snippet:
```kusto
let UnitPriceStandard = <UnitPriceStandard>;
let UnitPricePremium  = <UnitPricePremium>;
BillingUsage_Daily
| where Date >= ago(60d)
| where SKU in ('Free','Standard','Premium') and ResourceId has 'microsoft.signalrservice/signalr'
| join kind=inner (ResourceMetrics | where Date >= ago(60d)) on Date, ResourceId  // align to activity
| join kind=leftouter SubscriptionMappings on SubscriptionId                      // enrich with cohorts
| extend Revenue = case(
    SKU == 'Standard', UnitPriceStandard * Quantity,
    SKU == 'Premium',  UnitPricePremium  * Quantity,
    0.0)
| summarize PaidUnits = sumif(Quantity, SKU in ('Standard','Premium')),
            Revenue   = sum(Revenue)
  by Date, CustomerType, BillingType, SKU
```

- De-dup/latest snapshot per period
  - Description: Choose the latest row per period (e.g., latest monthly run) from snapshot tables.
  - Snippet (row_number pattern as used in queries):
```kusto
ChurnCustomers_Monthly
| where ServiceType == 'SignalR'
| order by Month asc, RunDay desc
| extend Rank = row_number(1, prev(Month) != Month)
| where Rank == 1
```
  - Snippet (arg_max alternative):
```kusto
ChurnCustomers_Monthly
| where ServiceType == 'SignalR'
| summarize arg_max(RunDay, *) by Month
```

- Important filters (defaults and exclusions)
  - Description: Apply service, SKU, and internal subscription exclusions consistently.
  - Snippet:
```kusto
| where ResourceId has 'microsoft.signalrservice/signalr'
| where SKU !in ('MessageCount','MessageCountPremium')
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
```

- Important definitions
  - AI cohort (resource-keyword allowlist):
```kusto
| where ResourceId has 'gpt' or ResourceId has 'ai' or ResourceId has 'ml' or ResourceId has 'cognitive'
   or ResourceId contains 'openai' or ResourceId contains 'chatgpt'
```
  - Active resource flag:
```kusto
| summarize HasConnection = max(MaxConnectionCount) > 0 by ResourceId
```
  - Has autoscale signals among premium:
```kusto
FeatureTrack_AutoScale_Daily
| where Date >= startofweek(now(), -12) and ResourceId has '/signalr/'
| summarize AutoscaleResourceCount = dcount(ResourceId) by Week = startofweek(Date)
| join kind=inner (
    BillingUsage_Daily
    | where Date >= startofweek(now(), -12) and SKU == 'Premium' and ResourceId has '/signalr/'
    | summarize TotalPremiumResource = dcount(ResourceId) by Week = startofweek(Date)
) on Week
| extend PercentInPremium = 1.0 * AutoscaleResourceCount / TotalPremiumResource
```

- ID parsing/derivation and normalization
  - Description: Extract SubscriptionId from ARM resource ID; normalize casing; remove replica suffix.
  - Snippet:
```kusto
| parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
| extend ResourceId = tolower(iif(ResourceId has '/replicas/', substring(ResourceId, 0, indexof(ResourceId, '/replicas/')), ResourceId))
```

- Sharded union (EU silo + global) with normalization
  - Description: Merge same-schema EU variants and standardize fields before aggregation.
  - Snippet:
```kusto
FeatureTrackV2_Daily
| union FeatureTrackV2_EU_Daily
| where Date >= startofweek(now()) - 56d
| extend Date = startofday(Date)
| project-away Properties
| summarize Requests = sum(RequestCount) by Week = startofweek(Date), Feature, Category
```

- Multi-slice completeness gate (goal-aligned monthly snapshots)
  - Description: Align facts to end-of-month snapshots when combining with goals.
  - Snippet:
```kusto
let Current = toscalar(BillingUsage_Daily | top 1 by Date desc | project Date);
BillingUsage_Daily
| where Date >= datetime(20201201) and Date < startofmonth(Current)
| extend TimeStamp = startofday(endofmonth(Date))
| summarize Subscriptions = dcount(SubscriptionId, 4) by TimeStamp
| join kind=fullouter (datatable(TimeStamp: datetime, SubscriptionGoal: real)[
    datetime(2025-06-30), 395,
    datetime(2025-07-31), 426
]) on TimeStamp
| project TimeStamp, Subscriptions, SubscriptionGoal
```


## Example Queries (with explanations)

1) Revenue by Service and SKU (SignalR vs Web PubSub)
- Description: Estimates revenue by multiplying Quantity with unit prices, splits by service type using ResourceId, excludes internal subscriptions and message count SKUs, and aligns to activity via MaxConnectionCount_Daily. Output pivots Service label via pack/mv-expand. Adapt by changing time window, unit prices, or segment dimensions.
```kusto
let raw = BillingUsage_Daily
| where Date >= ago(30d) and SKU !in ('MessageCount', 'MessageCountPremium') and SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| extend Role = tolower(ResourceId)
| join kind = inner (MaxConnectionCount_Daily | where Date >= ago(60d) 
| project Date, Role = tolower(Role)) on Date, $left.Role == $right.Role
| extend isAsrs = ResourceId has 'microsoft.signalrservice/signalr', isAwps = ResourceId has 'microsoft.signalrservice/webpubsub',
Income = case(SKU == 'Free', 0.0, SKU == 'Standard', 1.61, SKU == 'Premium', 2.0, 1.0)*Quantity
| summarize Income = sum(Income) by Date, SKU, SubscriptionId, isAsrs, isAwps
| join kind = leftouter SubscriptionMappings on SubscriptionId;
raw
| summarize Total = sum(Income), Asrs = sumif(Income, isAsrs), Awps = sumif(Income, isAwps) by Date, SKU, CustomerType, SegmentName
| extend Temp = pack(' JOIN(OR)', Total, 'SignalR', Asrs, 'WebPubSub', Awps)
| mv-expand kind = array Temp
| project Date, SKU, CustomerType, SegmentName, Service = tostring(Temp[0]), Income = toreal(Temp[1])
| union (raw
| summarize Total = sum(Income), Asrs = sumif(Income, isAsrs), Awps = sumif(Income, isAwps) by Date, SKU = ' JOIN(OR)', CustomerType, SegmentName
| extend Temp = pack(' JOIN(OR)', Total, 'SignalR', Asrs, 'WebPubSub', Awps)
| mv-expand kind = array Temp
| project Date, SKU, CustomerType, SegmentName, Service = tostring(Temp[0]), Income = toreal(Temp[1]))
```

2) Consumption by Service and SKU
- Description: Similar to revenue but computes consumption as Quantity * 24, aligns to activity via MaxConnectionCount_Daily, then splits into SignalR vs Web PubSub totals. Adapt by adjusting time range or replacing the multiplier if needed.
```kusto
let raw = BillingUsage_Daily
| where Date >= ago(30d) and SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| extend Role = tolower(ResourceId)
| join kind = inner (MaxConnectionCount_Daily | where Date >= ago(60d) 
| project Date, Role = tolower(Role)) on Date, $left.Role == $right.Role
| extend isAsrs = ResourceId has 'microsoft.signalrservice/signalr', isAwps = ResourceId has 'microsoft.signalrservice/webpubsub'
| summarize Consumption = sum(Quantity) * 24 by Date, SKU, SubscriptionId, isAsrs, isAwps
| join kind = leftouter SubscriptionMappings on SubscriptionId;
raw
| summarize Total = sum(Consumption), Asrs = sumif(Consumption, isAsrs), Awps = sumif(Consumption, isAwps) by Date, SKU, CustomerType, SegmentName
| extend Temp = pack(' JOIN(OR)', Total, 'SignalR', Asrs, 'WebPubSub', Awps)
| mv-expand kind = array Temp
| project Date, SKU, CustomerType, SegmentName, Service = tostring(Temp[0]), Consumption = toreal(Temp[1])
| union (raw
| summarize Total = sum(Consumption), Asrs = sumif(Consumption, isAsrs), Awps = sumif(Consumption, isAwps) by Date, SKU = ' JOIN(OR)', CustomerType, SegmentName
| extend Temp = pack(' JOIN(OR)', Total, 'SignalR', Asrs, 'WebPubSub', Awps)
| mv-expand kind = array Temp
| project Date, SKU, CustomerType, SegmentName, Service = tostring(Temp[0]), Consumption = toreal(Temp[1]))
```

3) Monthly Subscription Totals with Activity Gate (SignalR)
- Description: Counts resources by day, normalizes HasConnection from ResourceMetrics, and gates to EndDate (last common regional day). Summarize by SKU/Region/HasConnection. Adapt for Web PubSub by changing provider filter.
```kusto
//DailyResource(7, 61)
let EndDate = toscalar(BillingUsage_Daily | where Date > ago(10d) and Region in ('australiaeast', 'westeurope') 
| summarize counter = dcount(Region) by Date | where counter >= 2 | top 1 by Date desc | project Date);
BillingUsage_Daily
| where Date > ago(61d) and Date <= EndDate and ResourceId has 'microsoft.signalrservice/signalr' 
| extend SubscriptionId = tostring(split(ResourceId, '/')[2])
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
| summarize SKU = max(SKU), Region = max(Region) by Date, ResourceId
| join kind = leftouter ResourceMetrics on Date, ResourceId 
| extend HasConnection = iif(isempty(ResourceId1), false, MaxConnectionCount > 0)
| summarize Total = dcount(ResourceId) by Date, SKU, Region, HasConnection
```

4) Premium Autoscale Adoption (SignalR)
- Description: Share of premium SignalR resources that emitted autoscale signals in the week. Joins autoscale feature tracker with premium denominator. Adapt for Web PubSub by changing provider path.
```kusto
FeatureTrack_AutoScale_Daily
| where Date >= startofweek(now(), -12) and SubscriptionId !in (SignalRTeamInternalSubscriptionIds) and ResourceId has '/signalr/'
| summarize ResourceCount = dcount(ResourceId) by Week = startofweek(Date)
| join kind = inner (BillingUsage_Daily 
| where Date >= startofweek(now(), -12) and SubscriptionId !in (SignalRTeamInternalSubscriptionIds) and SKU == 'Premium' and ResourceId has '/signalr/'
| summarize TotalResource = dcount(ResourceId) by Week = startofweek(Date)) on Week
| extend PercentInPremium = 1.0*ResourceCount/TotalResource
| project-away Week1
```

5) Top Subscriptions Enrichment (SignalR)
- Description: Enrich top SignalR subscriptions with recent revenue, connections, messages, resource count via per-day dimensions and expand into (Category, Value) pairs. Adapt by changing date window or Service filter.
```kusto
let label = 'microsoft.signalrservice/signalr';
Cached_TopSubscriptions_Snapshot
| where Service == 'SignalR'
| project SubscriptionId
| join kind = inner (ResourceMetrics | where Date > startofday(now(), -29) and ResourceId has label
| parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
| summarize MaxConnectionCount = sum(MaxConnectionCount), MessageCount = sum(SumMessageCount) by Date, SubscriptionId) on SubscriptionId
| join kind = inner (BillingUsage_Daily | where Date > startofday(now(), -29) and ResourceId has label
| extend Revenue = case(SKU=='Standard', 1.61, SKU=='Premium', 2.0, SKU=='Free', 0.0, 1.0) * Quantity
| summarize Revenue = sum(Revenue), PaidUnits = sumif(Quantity, SKU in ('Standard', 'Premium')), ResourceCount = dcount(ResourceId) by Date, SubscriptionId) on SubscriptionId, Date
| extend Temp = pack('PaidUnits', PaidUnits, 'Revenue', Revenue, 'Messages', MessageCount, 'Connections', MaxConnectionCount, 'Resources', ResourceCount)
| mv-expand kind = array Temp
| project Date, SubscriptionId, Category = tostring(Temp[0]), Value = toreal(Temp[1])
```

6) QoS Rolling Windows (SignalR Operation QoS)
- Description: Computes 7-day and 28-day rolling QoS as of the last available QoS date; uses a dateFilter self-join to anchor rolling windows. Adapt by changing resourceId contains 'webpubsub' for Web PubSub.
```kusto
let dateFilter = OperationQoS_Daily
| top 1 by env_time desc
| project env_time, fakeKey = 1;
OperationQoS_Daily
| where env_time > ago(10d) and resourceId has 'microsoft.signalrservice/signalr'
| extend fakeKey = 1
| join kind = inner dateFilter on fakeKey
| where env_time > env_time1 - 7d
| summarize Qos = iif(sum(totalTimeSec) == 0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec)) by Date = env_time1, Type = 'Rolling7'
| union (
OperationQoS_Daily
| where env_time > ago(30d) and resourceId contains 'microsoft.signalrservice/signalr'
| extend fakeKey = 1
| join kind = inner dateFilter on fakeKey
| where env_time > env_time1 - 28d
| summarize Qos = iif(sum(totalTimeSec) == 0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec)) by Date = env_time1, Type = 'Rolling28')
```

7) AI Cohort Monthly Growth and Goals
- Description: Builds 28-day rolling AI cohort counts for latest and prior periods, unions historical month-end counts, and joins to monthly growth goals. Adapt keywords for cohort definition or extend window length.
```kusto
let NonEU = BillingUsage_Daily 
    | where Region == 'australiaeast' 
    | top 1 by Date desc 
    | project Date;
let EU = BillingUsage_Daily 
    | where Region == 'westeurope' 
    | top 1 by Date desc 
    | project Date;
let Current = toscalar(NonEU | union EU | top 1 by Date asc);
let DoM = 28d; // 28-day rolling window
let LatestPeriod = BillingUsage_Daily
| where Date > Current - DoM and Date <= Current
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| where ResourceId has 'gpt' or 
       ResourceId has 'ai' or 
       ResourceId has 'ml' or 
       ResourceId has 'cognitive' or 
       ResourceId contains 'openai' or 
       ResourceId contains 'chatgpt'
| extend 
    IsSignalR = ResourceId has 'microsoft.signalrservice/signalr', 
    IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub',
    Month = startofday(Current)
| summarize 
    SubscriptionCnt = dcount(SubscriptionId), 
    SignalR = dcountif(SubscriptionId, IsSignalR, 4), 
    WebPubSub = dcountif(SubscriptionId, IsWebPubSub, 4) 
    by Month;
let LatestPeriodBeforeLast = BillingUsage_Daily
| where Date > Current - 2*DoM and Date <= Current - DoM
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| where ResourceId has 'gpt' or 
       ResourceId has 'ai' or 
       ResourceId has 'ml' or 
       ResourceId has 'cognitive' or 
       ResourceId contains 'openai' or 
       ResourceId contains 'chatgpt'
| extend 
    IsSignalR = ResourceId has 'microsoft.signalrservice/signalr', 
    IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub',
    Month = startofday(Current) - 1h
| summarize 
    SubscriptionCnt = dcount(SubscriptionId), 
    SignalR = dcountif(SubscriptionId, IsSignalR, 4), 
    WebPubSub = dcountif(SubscriptionId, IsWebPubSub, 4) 
    by Month;
let Historical = BillingUsage_Daily
| where Date >= endofmonth(now(), -14) and Date < startofmonth(Current)
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| where ResourceId has 'gpt' or 
       ResourceId has 'ai' or 
       ResourceId has 'ml' or 
       ResourceId has 'cognitive' or 
       ResourceId contains 'openai' or 
       ResourceId contains 'chatgpt'
| extend 
    IsSignalR = ResourceId has 'microsoft.signalrservice/signalr', 
    IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub',
    Month = startofday(endofmonth(Date))
| summarize 
    SubscriptionCnt = dcount(SubscriptionId), 
    SignalR = dcountif(SubscriptionId, IsSignalR, 4), 
    WebPubSub = dcountif(SubscriptionId, IsWebPubSub, 4) 
    by Month;
LatestPeriod
| union LatestPeriodBeforeLast
| union Historical
| join kind = fullouter (
    datatable(Month: datetime, SubscriptionGoal: int, SubscriptionGrowthGoal: real)[
        datetime(2025-06-30), 395, 0.08,
        datetime(2025-07-31), 426, 0.08,
        datetime(2025-08-31), 460, 0.08,
        datetime(2025-09-30), 496, 0.08,
        datetime(2025-10-31), 535, 0.08,
        datetime(2025-11-30), 577, 0.08,
        datetime(2025-12-31), 623, 0.08
    ]
) on Month
| extend Month = iif(isempty(Month), Month1, Month)
| project-away Month1
```

8) Combined OKR ARR Snapshot with Monthly Goals
- Description: Joins pre-aggregated ARR snapshot to inline monthly goals, normalizes TimeStamp, and filters to a historical window. Adapt by changing goal values or time horizon.
```kusto
Cached_DtOKRARR_Snapshot
| join kind = fullouter (datatable(TimeStamp: datetime, TotalGoal: real, TotalGrowthGoal: real)[
datetime(2025-06-30), 35839557, 0.02,
datetime(2025-07-31), 36556348.1, 0.02,
datetime(2025-08-31), 37287475.1, 0.02,
datetime(2025-09-30), 38033224.6, 0.02,
datetime(2025-10-31), 38793889.1, 0.02,
datetime(2025-11-30), 39569766.9, 0.02,
datetime(2025-12-31), 40361162.2, 0.02]) on TimeStamp
| extend TimeStamp = iif(isempty(TimeStamp), TimeStamp1, TimeStamp)
| project-away TimeStamp1
| where TimeStamp >= startofmonth(now(), -35)
```


## Reasoning Notes (only if uncertain)
- Timezone: Not explicitly stated. We adopt UTC (most ADX clusters store timestamps UTC), and we recommend avoiding current-day data unless completeness is verified.
- Internal subscription list: SignalRTeamInternalSubscriptionIds appears as a function/table; exact content is unknown. We apply it by default to exclude internal usage in business metrics.
- Unit prices: Queries hardcode 1.61 (Standard) and 2.0 (Premium). Treat these as placeholders (<UnitPriceStandard>, <UnitPricePremium>) in reusable queries because pricing may change or vary by offer.
- Activity alignment: Several queries join to MaxConnectionCount_Daily or ResourceMetrics to ensure “active” or present resources. For generalized counting, we keep this alignment to avoid counting dormant entities.
- Replica normalization: Some metrics strip '/replicas/' in ResourceId to consolidate identities. If a report requires per-replica detail, skip this normalization.
- EU sharding: For complete coverage, union EU-specific tables (FeatureTrackV2_EU_Daily, Runtime* _EU). If privacy or residency constraints apply, verify allowed unions across regions.
- Completeness gating: We used 'australiaeast' and 'westeurope' as sentinel slices based on provided queries. If product expands to new sentinel regions, the gate should be updated.
- Retention snapshots: Period coverage is defined by StartDate/EndDate windows in snapshots. For periods outside these windows, results will drop unless extrapolated; ensure alignment with cohort definitions.
- Cohort keywords (AI): The allowlist is string-based and may over/under-include. If more precise tagging exists, prefer it, else keep this conservative filter.