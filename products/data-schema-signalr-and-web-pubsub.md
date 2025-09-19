# SignalR and Web PubSub - Product and Data Overview Template

## 1. Product Overview

SignalR and Web PubSub are Azure real-time messaging services enabling low-latency, persistent connections and pub/sub patterns for web and server applications. This onboarding provides PMAgent with schema and playbook context to interpret product-specific telemetry and business metrics for SignalR and Web PubSub across revenue, usage, connections/messages, feature adoption, and subscription/customer analytics.

## 2. Data Platform Overview

- Data Storage: Azure Data Explorer (ADX)
- Product:
SignalR and Web PubSub
- Product Nick Names: 
**[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations.
- Kusto Cluster:
signalrinsights.eastus2
- Kusto Database:
SignalRBI
- Access Control:
**[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed groups/users here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

# Kusto Query Playbook: SignalR and Web PubSub

## Overview
- Product: SignalR and Web PubSub
- Summary: Power BI M blocks with KQL queries targeting Azure Data Explorer cluster signalrinsights.eastus2 database SignalRBI for OKR, usage, revenue, connections/messages, feature tracking, customer/subscription metrics, and auxiliary sources (ARMProd, DDTelInsights).
- Primary cluster/database: signalrinsights.eastus2 / SignalRBI
  - Alternates used in cross-source queries: armprodgbl.eastus (ARM control-plane logs), ddtelinsights (WebTools telemetry)

## Conventions & Assumptions

### Time semantics
- Observed timestamp columns:
  - Date (most facts and curated snapshots)
  - env_time (QoS tables)
  - Week/Month are derived via startofweek()/startofmonth()
  - TIMESTAMP (ARM control-plane)
  - AdvancedServerTimestampUtc (WebTools_Raw)
- Canonical Time Column: TimeCol (alias to the active time column)
  - Alias patterns:
    - project-rename TimeCol = Date
    - project-rename TimeCol = env_time
    - extend Week = startofweek(Date); extend Month = startofmonth(Date)
- Typical windows and binning:
  - Daily facts: last 28–60 days; frequently exclude the current day
  - Weekly: startofweek(now(), -8 to -12) and Date < startofweek(now())
  - Monthly: startofmonth(now(), -12 to -16) and Date < startofmonth(now())
  - QoS rolling views: last 7 or 28 days relative to the latest available day
- Timezone: unknown. Treat all bins as UTC by default. Avoid relying on “today” without a completeness gate.

### Freshness & Completeness Gates
- Daily tables update daily; weekly/monthly snapshots on period close. Cached_* snapshots are curated and refreshed on their cadence.
- Current-day data is often incomplete; many queries explicitly avoid including current week/month/day.
- Effective end time patterns seen:
  - Multi-slice gate using two sentinel regions to pick the latest complete Date:
    - Example sentinel regions: 'australiaeast' and 'westeurope'
- Recommended practice:
  - For daily windows, cap end at the latest day where ≥N sentinel slices reported
  - For weekly/monthly, restrict to Date < startofweek(now()) or Date < startofmonth(now())

Multi-slice gate template:
```kusto
// Pick the latest fully ingested Date across sentinel regions
let SentinelRegions = dynamic(['australiaeast','westeurope']);
let EndDate =
    toscalar(
        BillingUsage_Daily
        | where Date > ago(10d) and Region in (SentinelRegions)
        | summarize RegionsReporting = dcount(Region) by Date
        | where RegionsReporting >= array_length(SentinelRegions)
        | top 1 by Date desc
        | project Date
    );
```

### Joins & Alignment
- Frequent keys:
  - SubscriptionId (GUID; also derivable from ResourceId)
  - ResourceId (fully-qualified ARM id; normalize case; strip replicas)
  - Region, SKU, ServiceType/Kind (after enriching)
- Typical join kinds:
  - inner: activity gating with MaxConnectionCount_Daily or ResourceMetrics
  - leftouter: enrichment with SubscriptionMappings, RPSettingLatest
- Pre-join alignment and hygiene:
  - Normalize case: extend ResourceId = tolower(ResourceId)
  - Strip replicas: iif(ResourceId has '/replicas/', substring(ResourceId, 0, indexof(ResourceId, '/replicas/')), ResourceId)
  - Parse subscription: parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
  - Resolve duplicates: project-away columns with suffixes (e.g., *1), or coalesce()
  - Prefer startofday()/startofweek()/startofmonth() alignment on both sides prior to join

### Filters & Idioms
- Common service filters:
  - ResourceId has 'microsoft.signalrservice/signalr'
  - ResourceId has 'microsoft.signalrservice/webpubsub'
- Internal exclusion:
  - SubscriptionId !in (SignalRTeamInternalSubscriptionIds) or SignalRTeamInternalSubscriptionIds()
- SKU handling:
  - SKUs: 'Free','Standard','Premium'
  - Exclude 'MessageCount','MessageCountPremium' in revenue/consumption analyses
- Text operators:
  - has (tokenized match), contains (substring), startswith
  - Case normalization often applied: tolower(ResourceId)
- Counting:
  - dcount(key, 3 or 4) used to stabilize HLL precision in subscription/resource/customer counts

### Cross-cluster/DB & Sharding
- External sources:
  - ARM control-plane: cluster('armprodgbl.eastus').database('<db>').Unionizer(...)
  - Dev tools telemetry: cluster('ddtelinsights').database('<db>').WebTools_Raw
- Same-schema shards:
  - EU vs non-EU tables: FeatureTrackV2_Daily and FeatureTrackV2_EU_Daily; union then normalize time/keys before summarizing
- Pattern:
```kusto
union isfuzzy=true
    FeatureTrackV2_Daily,
    FeatureTrackV2_EU_Daily
| extend Date = startofday(Date), ResourceId = tolower(ResourceId)
| summarize ... by Date, <dims>
```

### Table classes
- Fact (daily/events): BillingUsage_Daily, ResourceMetrics, FeatureTrack*_*_Daily, QoS tables, ManageRPQosDaily, ManageResourceTags
- Snapshot (latest/periodic state): Cached_* snapshots, Retention snapshots, CustomerModel, Cached_TopSubscriptions_Snapshot
- Pre-aggregated: Cached_ZnOKREstRevenueWeekly/Monthly_Snapshot, Cached_CuOKRConsumption_*_Snapshot, Cached_SubsTotal* snapshots
- Guidance:
  - Use pre-aggregated Cached_* for OKR/reporting views
  - Use BillingUsage_Daily for recomputing revenue/consumption with new dimensions
  - Use ResourceMetrics for runtime activity, active gating, live ratio

## Entity & Counting Rules (Core Definitions)

- Entity model:
  - Resource → Subscription → Customer
  - Keys:
    - Resource: ResourceId (normalize case; strip '/replicas/')
    - Subscription: SubscriptionId (from facts or parsed from ResourceId)
    - Customer: CloudCustomerGuid or P360_ID (from SubscriptionMappings/CustomerModel)
- Standard groupings:
  - Resource-level: ResourceId, Region, SKU, HasConnection, LiveRatio
  - Subscription-level: SubscriptionId, CustomerType, BillingType, SegmentName, SKU
  - Customer-level: CloudCustomerGuid, SegmentName, CustomerType
- Active definitions:
  - HasConnection = MaxConnectionCount > 0 derived from ResourceMetrics (or inner join existence via MaxConnectionCount_Daily)
  - LiveRatio buckets (observed):
    - Weekly: Swift vs Occasional based on ActiveDays threshold (ActiveDays < 3 → Swift; else Occasional)
    - Monthly: Swift (<3), Occasional (<10), else Dedicate
- Revenue computation:
  - Income = Quantity × UnitPrice(SKU)
  - Use placeholders for unit prices:
    - <UnitPrice_Free> = 0.0
    - <UnitPrice_Standard>, <UnitPrice_Premium>, <UnitPrice_Default>
  - Exclude MessageCount SKUs when computing subscription-level revenue
- Consumption normalization:
  - NormalizedConsumption = sum(Quantity) × 24 (proxy seen in queries)
- “AI customer” cohort (observed pattern):
  - ResourceId contains any of: 'gpt', 'ai', 'ml', 'cognitive', 'openai', 'chatgpt'
- Counting rules:
  - Use dcount(key, 3 or 4) for SubscriptionCnt/ResourceCnt/CustomerCnt
  - Avoid double-counting pre-aggregated snapshots; respect their dimensioning

## Canonical Tables for SignalR and Web PubSub (cluster: signalrinsights.eastus2, database: SignalRBI)

Notes
- Timezone: unknown. Interpret all “today/now” uses carefully; avoid current-day windows for partially-ingested days.
- Freshness conventions: Daily tables are expected to refresh daily; Weekly/Monthly snapshots update on their period close; “Cached_*_Snapshot” are curated summary layers refreshed on their cadence.
- Common cross-cutting filters seen in queries:
  - Time: Date >= ago(30d) (daily), last 8–12 weeks (weekly), last 8–16 months (monthly).
  - Service selector: ResourceId has 'microsoft.signalrservice/signalr' or 'microsoft.signalrservice/webpubsub'.
  - Exclude internal tenants: SubscriptionId !in (SignalRTeamInternalSubscriptionIds).
  - SKU segmentation: Free, Standard, Premium; exclude MessageCount/MessageCountPremium when computing revenue/consumption.
  - Active resource guard: inner join with recent resources that reported MaxConnectionCount (via ResourceMetrics joins).
- Cost abstraction: When revenue is computed from Quantity and SKU, treat unit prices as placeholders (e.g., <UnitPrice_Standard>, <UnitPrice_Premium>) instead of hardcoding.

High-priority tables are listed first, followed by Normal and Low.

---

### BillingUsage_Daily
- Priority: High
- What this table represents: Daily fact grain for billed usage per resource/subscription/region/SKU; base for both revenue and consumption calculations. Zero rows for a day implies no billed usage ingested for that scope.
- Freshness expectations: Daily. Most queries use 28–60 day windows and avoid current partial day.
- When to use / When to avoid:
  - Use: revenue by SKU and segment; subscription counts by SKU; message/connection billing normalization; service mix (SignalR vs WebPubSub).
  - Use: filter by ResourceId service type; exclude internal subscriptions.
  - Avoid: operational metrics (connections/messages) at runtime; instead use ResourceMetrics. Avoid using MessageCount SKUs when analyzing revenue/consumption per unit pricing.
- Similar tables & how to choose:
  - ResourceMetrics: for runtime signals (connections/messages). Join both for revenue + activity.
  - Cached_* snapshots: curated aggregates; prefer snapshots for OKR and pre-joined segment analysis to reduce compute.
- Common Filters:
  - Date windows (ago(30d), startofweek/month, normalized 28-day windows).
  - SubscriptionId !in (SignalRTeamInternalSubscriptionIds).
  - ResourceId has '/signalr/' or '/webpubsub/'.
  - SKU in ('Free','Standard','Premium') and often exclude 'MessageCount','MessageCountPremium'.
- Table columns:

  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | Date          | datetime | Usage day (UTC unknown). Use startofday normalization for joins. |
  | Region        | string   | Azure region of the resource. Often used to compute dual-region completeness checks. |
  | SubscriptionId| string   | Azure subscription GUID; key to segment mapping. |
  | ResourceId    | string   | Full Azure resource ID (may include '/replicas/'). |
  | SKU           | string   | Free/Standard/Premium/MessageCount/MessageCountPremium. |
  | Quantity      | real     | Daily billed quantity. Multiply by unit price for revenue; multiply by 24 for normalized consumption in some queries. |
- Column Explain:
  - Date: Primary time axis; use startofday/startofweek/startofmonth for alignment.
  - SubscriptionId: Join to SubscriptionMappings for SegmentName, BillingType, CustomerType.
  - ResourceId: Filter for service type; derive primary resource vs replicas; parse subscription via split(ResourceId, '/')[2].
  - SKU: Segment revenue/consumption; often exclude message SKUs for core revenue views.
  - Quantity: Used to compute revenue with SKU-based unit pricing and normalize consumption.

---

### ResourceMetrics
- Priority: High
- What this table represents: Daily fact of runtime telemetry aggregates per resource (connections/messages/errors/operations). Zero rows imply no metrics observed/ingested for that resource-day.
- Freshness expectations: Daily; aggregated by Date; heavy use of week/month rollups and maxima across a week.
- When to use / When to avoid:
  - Use: connection/message volumes; detect active resources (MaxConnectionCount > 0); categorize live ratio by active days.
  - Avoid: billing computations (use BillingUsage_Daily) or CRM segmentation (use SubscriptionMappings).
- Similar tables & how to choose:
  - BillingUsage_Daily for financial computations.
  - FeatureTrack* for feature usage per resource per day.
- Common Filters:
  - Date windows (60d, 8–12 weeks, 12 months).
  - ResourceId has ‘signalr’ or ‘webpubsub’.
  - Parse SubscriptionId from ResourceId for joins and internal exclusion.
- Table columns:

  | Column             | Type     | Description or meaning |
  |--------------------|----------|------------------------|
  | Date               | datetime | Metric date. |
  | Region             | string   | Region where metrics were recorded. |
  | ResourceId         | string   | Full resource ID (lowercased in many joins; strip '/replicas/'). |
  | SumMessageCount    | real     | Sum of message counts. |
  | MaxConnectionCount | real     | Peak concurrent connections (key signal of “active”). |
  | AvgConnectionCount | real     | Average concurrent connections. |
  | SumSystemErrors    | real     | Aggregate system failures. |
  | SumTotalOperations | real     | Aggregate operation volume. |
- Column Explain:
  - MaxConnectionCount: used as an “active proof” to include resources/subscriptions.
  - SumMessageCount: workload intensity proxy; used for top subs analysis.
  - Date + ResourceId: join back to BillingUsage_Daily to build holistic KPIs.

---

### SubscriptionMappings
- Priority: High
- What this table represents: Subscription → customer/segment metadata mapping. Snapshot/dimension table.
- Freshness expectations: Updated when CRM/offer metadata changes; cadence not specified (unknown).
- When to use / When to avoid:
  - Use: segment aggregations (SegmentName), customer type (Internal/External), OfferType/OfferName, BillingType, P360/C360 ids.
  - Avoid: time-series facts; no usage values here.
- Similar tables & how to choose:
  - CustomerModel enriches top-subscription details; use SubscriptionMappings for broad coverage in aggregations.
- Common Filters:
  - Join key SubscriptionId from fact tables.
  - Read CloudCustomerGuid, SegmentName, BillingType for grouping.
- Table columns:

  | Column            | Type    | Description or meaning |
  |-------------------|---------|------------------------|
  | P360_ID           | string  | Customer id in Partner 360 ecosystem. |
  | CloudCustomerGuid | string  | Customer GUID. |
  | SubscriptionId    | string  | Subscription GUID; primary join key. |
  | CustomerType      | string  | Internal/External. |
  | CustomerName      | string  | Display name. |
  | SegmentName       | string  | Segment grouping. |
  | OfferType         | string  | Offer classification. |
  | OfferName         | string  | Offer name. |
  | BillingType       | string  | EA/PayG/etc.; used to derive UsageType. |
  | WorkloadType      | string  | Workload category. |
  | S500              | string  | Additional segment/flag (meaning per org). |
- Column Explain:
  - SubscriptionId: always join to facts.
  - CustomerType/BillingType/SegmentName: core dimensions in most pivots.

---

### CustomerModel
- Priority: High
- What this table represents: Curated model for top subscriptions/customers with revenue, usage (connections/messages), retention flags, and CRM links. Likely snapshot fact enriched with CRM metadata. Zero rows for a subscription means not in the top set.
- Freshness expectations: Unknown; used with “Cached_TopSubscriptions_Snapshot” within 28–29 day windows.
- When to use / When to avoid:
  - Use: top customers analysis, with revenue, connections, messages, retention (IsNew/IsRetained).
  - Avoid: raw usage/revenue computations; use underlying facts for full coverage.
- Similar tables & how to choose:
  - Cached_TopSubscriptions_Snapshot is the primary snapshot for time-series expansion; CustomerModel provides enrichment fields (names/TPID/rates).
- Common Filters:
  - Join on SubscriptionId with Cached_TopSubscriptions_Snapshot; restrict to last ~29 days.
- Table columns (observed from queries; full schema access denied):
  - SubscriptionId (string)
  - Revenue (real)
  - MaxConnection (long)
  - MessageCount (long)
  - Rate (real)
  - CloudCustomerName (string)
  - CustomerType (string)
  - TPName (string)
  - BillingType (string)
  - OfferName (string)
  - OfferType (string)
  - P360_ID (string)
  - TPID (string) [implied in C360Url construction]
- Column Explain:
  - Revenue/MaxConnection/MessageCount: used for KPI ranking.
  - CustomerType/BillingType/Offer*: segmentation dimensions for top lists.

---

### Cached_ZnOKRARR_Snapshot
- Priority: High
- What this table represents: Snapshot time series for ARR targets and actuals across SignalR/WebPubSub at monthly granularity.
- Freshness expectations: Monthly snapshots; extended with inline goals in queries.
- When to use / When to avoid:
  - Use: OKR ARR views and goal overlays.
  - Avoid: detailed revenue breakdown by SKU; use BillingUsage_Daily for granular analysis.
- Similar tables & how to choose:
  - Cached_DtOKRARR_Snapshot (if present) represents different scopes (Zn vs Dt).
- Common Filters:
  - Join to goal datatables on TimeStamp; select startofmonth windows.
- Table columns:

  | Column    | Type     | Description or meaning |
  |-----------|----------|------------------------|
  | TimeStamp | datetime | Snapshot month end/start. |
  | SignalR   | real     | ARR metric for SignalR. |
  | WebPubSub | real     | ARR metric for WebPubSub. |
- Column Explain:
  - TimeStamp: align to month; overlay with growth goals.

---

### Cached_ZnOKREstRevenueWeekly_Snapshot
- Priority: High
- What this table represents: Weekly revenue snapshot by SKU and segment for OKR tracking; curated result of revenue computations.
- Freshness expectations: Weekly.
- When to use / When to avoid:
  - Use: OKR revenue tracking by week, SKU, CustomerType/SegmentName.
  - Avoid: ad hoc revenue recomputation; use BillingUsage_Daily only if a new dimension is needed.
- Similar tables & how to choose:
  - Cached_ZnOKREstRevenueMonthly_Snapshot for monthly views.
- Common Filters:
  - Week windows before the current week.
- Table columns:

  | Column       | Type     | Description or meaning |
  |--------------|----------|------------------------|
  | Week         | datetime | Week bucket (startofweek). |
  | SKU          | string   | Free/Standard/Premium or aggregation token. |
  | CustomerType | string   | Internal/External. |
  | SegmentName  | string   | Segment grouping. |
  | Service      | string   | JOIN tokens or per-service splits. |
  | Income       | real     | Curated revenue metric. |
- Column Explain:
  - Income: already aggregated; do not double-aggregate across distinct dimension rows.

---

### Cached_ZnOKREstRevenueMonthly_Snapshot
- Priority: High
- What this table represents: Monthly revenue snapshot by SKU and segment for OKR tracking.
- Freshness expectations: Monthly.
- When to use / When to avoid: same as Weekly version; use for month views.
- Common Filters: Month ranges pre-current month.
- Table columns:

  | Column       | Type     | Description |
  |--------------|----------|------------|
  | Month        | datetime | Month bucket. |
  | SKU          | string   | SKU or aggregation token. |
  | CustomerType | string   | Internal/External. |
  | SegmentName  | string   | Segment grouping. |
  | Service      | string   | JOIN tokens or per-service splits. |
  | Income       | real     | Curated revenue metric. |
- Column Explain: Income by Month/SKU/segment.

---

### Cached_ZnOKRSubs_Snapshot
- Priority: High
- What this table represents: Snapshot monthly subscription counts for OKR targets (SignalR/WebPubSub).
- Freshness expectations: Monthly; often joined with goal series.
- When to use / When to avoid:
  - Use: total subs and service-specific subs vs goals.
  - Avoid: per-subscription detail; use SubscriptionFlow/Cached_SubsTotal snapshots.
- Common Filters: monthly windows.
- Table columns:

  | Column    | Type     | Description |
  |-----------|----------|-------------|
  | TimeStamp | datetime | Month bucket. |
  | SignalR   | long     | Subscription count for SignalR. |
  | WebPubSub | long     | Subscription count for WebPubSub. |
- Column Explain: Compare to growth goals.

---

### Cached_CuOKRConsumption_Snapshot
- Priority: High
- What this table represents: Curated consumption metric (normalized) with service splits for OKR tracking.
- Freshness expectations: Monthly snapshot.
- When to use / When to avoid:
  - Use: high-level consumption vs goals (SignalR vs WebPubSub).
  - Avoid: raw quantity-based analysis; use BillingUsage_Daily when recomputation needed.
- Common Filters: monthly timespan.
- Table columns:

  | Column      | Type     | Description |
  |-------------|----------|-------------|
  | TimeStamp   | datetime | Month bucket. |
  | Consumption | real     | Total normalized consumption. |
  | SignalR     | real     | Service split. |
  | WebPubSub   | real     | Service split. |
- Column Explain: Pre-aggregated; do not multiply again by 24 etc.

---

### Cached_CuOKRConsumptionWeekly_Snapshot
- Priority: High
- What this table represents: Weekly consumption snapshot by SKU and segment for OKR.
- Freshness expectations: Weekly.
- Table columns:

  | Column       | Type     | Description |
  |--------------|----------|-------------|
  | Week         | datetime | Week bucket. |
  | SKU          | string   | SKU or aggregation token. |
  | CustomerType | string   | Internal/External. |
  | SegmentName  | string   | Segment grouping. |
  | Service      | string   | JOIN tokens or per-service splits. |
  | Consumption  | real     | Curated consumption. |

---

### Cached_CuOKRConsumptionMonthly_Snapshot
- Priority: High
- What this table represents: Monthly consumption snapshot by SKU and segment for OKR.
- Freshness expectations: Monthly.
- Table columns:

  | Column       | Type     | Description |
  |--------------|----------|-------------|
  | Month        | datetime | Month bucket. |
  | SKU          | string   | SKU or aggregation token. |
  | CustomerType | string   | Internal/External. |
  | SegmentName  | string   | Segment grouping. |
  | Service      | string   | JOIN tokens or per-service splits. |
  | Consumption  | real     | Curated consumption. |

---

### FeatureTrackV2_Daily
- Priority: High
- What this table represents: Daily feature tracking per resource (feature/category, request counts). Fact table for product usage instrumentation.
- Freshness expectations: Daily; queries often normalize Date to startofday and aggregate by week.
- When to use / When to avoid:
  - Use: measure adoption of features like BlazorServerSide, Samples, Subprotocol, EventHandlerMessageEx, etc.
  - Avoid: connection/message volumes (ResourceMetrics) or billing (BillingUsage_Daily).
- Similar tables & how to choose:
  - FeatureTrackV2_EU_Daily for EU data; union both for global.
  - FeatureTrack_Daily (legacy) for some feature signals (Upstream failures etc.).
- Common Filters:
  - Date > startofweek(now()) - 56d.
  - ResourceId has '/signalr/' or '/webpubsub/' and SubscriptionId exclusion.
  - Join to BillingUsage_Daily to limit to active (SKU != MessageCount).
- Table columns:

  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Date          | datetime | Event day. |
  | Feature       | string   | Feature name (e.g., BlazorServerSide, Subprotocol). |
  | Category      | string   | Group/category; some normalized in queries. |
  | ResourceId    | string   | Resource emitting the feature event. |
  | SubscriptionId| string   | Subscription derived from ResourceId. |
  | Properties    | string   | Raw properties (JSON/string). |
  | RequestCount  | long     | Aggregated request count for that feature. |
- Column Explain:
  - Feature/Category: used as pivot dimensions.
  - RequestCount: sum for KPI; used to detect signals/flags (e.g., NeededScale).

---

### FeatureTrackV2_EU_Daily
- Priority: High
- What this table represents: EU partition of FeatureTrackV2_Daily; same schema.
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use: include for EU data or build global union.
  - Avoid: mixing without union when global is needed.
- Table columns: identical to FeatureTrackV2_Daily (see above).

---

### FeatureTrack_AutoScale_Daily
- Priority: High
- What this table represents: Feature tracking for AutoScale events per resource/day.
- Freshness expectations: Daily; aggregated to weekly in usage.
- When to use / When to avoid:
  - Use: measure AutoScale adoption within Premium SKU cohort.
  - Avoid: general runtime; use ResourceMetrics for connections/messages.
- Common Filters: Date >= startofweek(now(), -12); ResourceId has '/signalr/' or '/webpubsub/'; partner join to BillingUsage_Daily restricted to Premium.
- Table columns:

  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Date          | datetime | Event day. |
  | Region        | string   | Region (observed via summarize patterns). |
  | ResourceId    | string   | Resource id. |
  | SubscriptionId| string   | Subscription id. |
  | RequestCount  | long     | AutoScale-related request count. |
- Column Explain:
  - RequestCount: used to compute ResourceCount and PercentInPremium.

---

### FeatureTrack_Daily
- Priority: High
- What this table represents: Legacy/aux feature events per day; source for signals like Upstream_Exceptions, EventHandlerNotFoundException, ConnectionCountLimitReached.
- Freshness expectations: Daily.
- Common Filters: Date > startofday(now(), -29); ResourceId has '/signalr/' or '/webpubsub/'; join to derive SubscriptionId.
- Table columns:

  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Date          | datetime | Event day. |
  | Feature       | string   | Feature name (legacy signals). |
  | ResourceId    | string   | Resource id. |
  | SubscriptionId| string   | Subscription id (extracted/derived). |
  | RequestCount  | long     | Aggregated feature count. |
- Column Explain:
  - Feature: used to flag ServerSticky, NeededScale, MultiEndpoints, UpstreamFailure, etc.

---

### RuntimeResourceTags_Daily
- Priority: High
- What this table represents: Daily tag/flags for resources (AppService/StaticApps, Proxy usage, Samples, etc.). Snapshot-like boolean tag materialization by day.
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use: enrich top subscriptions with flags (IsAppService, IsStaticApps, IsProxy) and detect samples usage.
  - Avoid: usage counts/revenue.
- Common Filters: Date > startofday(now(), -29); ServiceType in ('SignalR','WebPubSub').
- Table columns:

  | Column        | Type  | Description |
  |---------------|-------|-------------|
  | Date          | datetime | Tag observation day. |
  | ResourceId    | string   | Resource id. |
  | SubscriptionId| string   | Subscription id. |
  | ServiceType   | string   | SignalR or WebPubSub. |
  | IsAppService  | bool     | Indicates App Service integration. |
  | IsStaticApps  | bool     | Indicates Static Web Apps integration. |
  | IsSample      | bool     | Resource flagged as sample. |
  | IsProxy       | bool     | Proxy mode used. |
  | HasFailure    | bool     | Failure observed. |
  | HasSuccess    | bool     | Success observed. |
  | Extra         | string   | Extra details. |
- Column Explain:
  - IsAppService/IsProxy/IsStaticApps: common enrichment in top-subs views.

---

### Cached_TopSubscriptions_Snapshot
- Priority: High
- What this table represents: Curated list of top subscriptions within recent window with revenue, usage (messages, connections), retention window (StartDate/EndDate), service label (SignalR/WebPubSub).
- Freshness expectations: Daily snapshot covering last ~28–29 days.
- When to use / When to avoid:
  - Use: to drive top-N dashboards and join with CustomerModel for names/TPIDs.
  - Avoid: global aggregations; use BillingUsage_Daily and ResourceMetrics directly.
- Common Filters:
  - Service == 'SignalR' or 'WebPubSub'; define IsNew/IsRetained over the 29-day window.
  - Join to ResourceMetrics/BillingUsage_Daily by Date and SubscriptionId for per-day breakdown.
- Table columns:

  | Column         | Type     | Description |
  |----------------|----------|-------------|
  | SubscriptionId | string   | Subscription id (join key). |
  | Revenue        | real     | Aggregated revenue within window. |
  | MaxConnection  | long     | Peak connections within window. |
  | MessageCount   | long     | Total messages within window. |
  | StartDate      | datetime | Observed first activity in window. |
  | EndDate        | datetime | Observed last activity in window. |
  | TopRevenue     | real     | Ranking measure (revenue). |
  | TopConnection  | long     | Ranking measure (connections). |
  | TopMessageCount| long     | Ranking measure (messages). |
  | Rate           | real     | Derived rate score. |
  | Service        | string   | 'SignalR' or 'WebPubSub'. |
- Column Explain:
  - StartDate/EndDate: support IsNew/IsRetained flags.
  - Category expansion pattern packs PaidUnits/Revenue/Messages/Connections/Resources.

---

### Cached_Asrs_TopCustomersWoW_v2_Snapshot
- Priority: High
- What this table represents: Curated week-over-week deltas and rankings for SignalR customers by category and SKU.
- Freshness expectations: Weekly.
- When to use / When to avoid:
  - Use: Top movers (ascending/descending delta); filter by Rank/Delta ranks.
  - Avoid: raw recompute; use this layer for WoW highlights.
- Common Filters: Category/SKU; Rank < 500.
- Table columns:

  | Column                    | Type     | Description |
  |---------------------------|----------|-------------|
  | P360_ID                   | string   | Customer id. |
  | P360_CustomerDisplayName  | string   | Display name. |
  | SKU                       | string   | SKU. |
  | CustomerType              | string   | Internal/External. |
  | BillingType               | string   | Billing type. |
  | Category                  | string   | Metric category (Revenue, Connections, etc.). |
  | CurrentValue              | real     | Current metric value. |
  | P360Url                   | string   | Deep-link to customer portal. |
  | LastDay                   | datetime | Reference date. |
  | UsageType                 | string   | Derived usage type. |
  | CurrentValue1             | real     | Additional current metric. |
  | PrevValue                 | real     | Prior value. |
  | W3Value                   | real     | 3-week value. |
  | DeltaValue                | real     | Difference metric. |
  | Rank                      | long     | Rank in category. |
  | W1Rank                    | long     | 1-week rank. |
  | W3Rank                    | long     | 3-week rank. |
- Column Explain:
  - DeltaValue/Rank fields: drive highlighting logic for dashboards.

---

### SubscriptionFlow_Weekly
- Priority: High
- What this table represents: Function/snapshot returning weekly subscription lifecycle flow (adds, retains, churn) per service type; used along with Cached_SubsTotalWeekly_Snapshot.
- Freshness expectations: Weekly.
- When to use / When to avoid:
  - Use: weekly flow trends; pair with totals snapshot.
  - Avoid: customer-level analysis; use Cached_TopSubscriptions_Snapshot or underlying facts.
- Similar tables & how to choose:
  - SubscriptionFlow_Monthly for month granularity.
- Common Filters: ServiceType == 'SignalR' or 'WebPubSub'.
- Table columns (from snapshot variant, not the function parameters):
  
  | Column       | Type     | Description |
  |--------------|----------|-------------|
  | Week         | datetime | Week bucket. |
  | ServiceType  | string   | SignalR/WebPubSub. |
  | SubscriptionId | string | Subscription id (used to dcount). |
  | Region       | string   | Region. |
  | SKU          | string   | SKU. |
  | HasConnection| bool     | Active flag (via ResourceMetrics). |
  | LiveRatio    | string   | Swift/Occasional/Dedicate classification. |
- Column Explain:
  - Use dcount(SubscriptionId, 3) to compute totals per dimension.

---

### SubscriptionFlow_Monthly
- Priority: High
- What this table represents: Monthly subscription lifecycle flow; analogous to weekly.
- Freshness expectations: Monthly.
- Columns: same as weekly but Month instead of Week.

  | Column       | Type     | Description |
  |--------------|----------|-------------|
  | Month        | datetime | Month bucket. |
  | ServiceType  | string   | SignalR/WebPubSub. |
  | SubscriptionId | string | Subscription id. |
  | Region       | string   | Region. |
  | SKU          | string   | SKU. |
  | HasConnection| bool     | Active flag. |
  | LiveRatio    | string   | Swift/Occasional/Dedicate. |

---

### Cached_SubsTotalWeekly_Snapshot
- Priority: High
- What this table represents: Weekly subscription totals with dimensions (Region, Offer*, BillingType, SKU, CustomerType, HasConnection, LiveRatio).
- Freshness expectations: Weekly.
- When to use / When to avoid:
  - Use: weekly subscription totals and customer totals via dcount.
  - Avoid: resource-level analysis; use ResourceFlow or ResourceMetrics joins.
- Table columns:

  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Week          | datetime | Week bucket. |
  | ServiceType   | string   | SignalR/WebPubSub. |
  | SubscriptionId| string   | Subscription id (for dcount). |
  | Region        | string   | Region. |
  | SKU           | string   | SKU. |
  | HasConnection | bool     | Active flag. |
  | LiveRatio     | string   | Swift/Occasional/Dedicate. |
- Column Explain:
  - Use join to SubscriptionMappings to surface OfferType/OfferName/BillingType/CustomerType for grouping.

---

### Cached_SubsTotalMonthly_Snapshot
- Priority: High
- What this table represents: Monthly subscription totals (same dimensionality as weekly).
- Freshness expectations: Monthly.
- Columns: same as weekly, but Month as the time bucket.

---

### OKRv2021
- Priority: Normal
- What this table represents: KPI series categorized by Category/Value at Date grain; pivoted for display.
- Freshness expectations: Unknown; historical KPI vault.
- When to use / When to avoid:
  - Use: historical KPI comparisons, pivot to shape.
  - Avoid: current OKR ARR/Revenue/Subscription targets (use the Cached_* OKR snapshots).
- Common Filters: Date >= datetime(20200701).
- Columns (inferred from usage):
  - Date (datetime), Category (string), Value (numeric)
- Column Explain: pivot(Category, sum(Value)) to wide views.

---

### ManageResourceTags
- Priority: Normal
- What this table represents: Management-plane operations tags on resources (RequestName, method/tags), counts per day.
- Freshness expectations: Daily; last 30-day windows common.
- When to use / When to avoid:
  - Use: analyze management activity patterns (create/update/delete/other), split by CustomerType.
  - Avoid: runtime (use FeatureTrack/ResourceMetrics) or billing.
- Common Filters: Date > ago(30d); filter out 'Microsoft.Authorization' and RequestName != 'Other'.
- Columns (inferred from queries):
  - Date (datetime), ResourceId (string), SubscriptionId (string), RequestName (string), Tags as RequestMethod (string), Count (numeric)
- Column Explain: Use summarize to compute OperationCount; join to SubscriptionMappings.

---

### ConnectionMode_Daily
- Priority: Normal
- What this table represents: Daily connection mode breakdown by ServiceMode (Serverless/Server), with connection counters.
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use: mode adoption analysis, serverless vs proxy/server mode mix.
  - Avoid: feature-level usage (FeatureTrack) or billing.
- Columns (inferred from queries):
  - Date (datetime), ResourceId (string), ServiceMode (string), ServerlessConnection (numeric), ProxyConnection (numeric)
- Column Explain: Summarize to compute ConnectionCount and ResourceCount.

---

### ChurnCustomers_Monthly
- Priority: Normal
- What this table represents: Monthly churn metrics for subscriptions/customers with Standard cohort focus; latest run per month.
- Freshness expectations: Monthly; multiple runs per month with “latest by RunDay”.
- Columns (inferred):
  - Month (datetime), RunDay (int), StandardChurn, Standard, Churn, Total
- Column Explain: compute StandardChurnRate = StandardChurn/Standard, OverallChurnRate = Churn/Total.

---

### ConvertCustomer_Weekly
- Priority: Normal
- What this table represents: Weekly conversion flows (Free→Standard/Premium; Standard→Premium) for each service type; latest run per week.
- Freshness expectations: Weekly.
- Columns (inferred):
  - Week (datetime), RunDay (int), FreeToPaid, FreeToStandard, FreeToPremium, StandardToPremium
- Column Explain: handle nulls and coalesce to 0 as shown in queries.

---

### KPIv2019
- Priority: Normal
- What this table represents: Legacy KPI history (from 2019); details not expanded in queries.
- Freshness expectations: Historical.
- Columns: not enumerated; treat as historical reference.

---

### SubscriptionRetentionSnapshot / CustomerRetentionSnapshot / ResourceRetentionSnapshot
- Priority: Normal
- What these tables represent: Retention cohort snapshots for subscription/customer/resource respectively; cohorts by StartDate with retention across months until EndDate.
- Freshness expectations: Monthly snapshots; used to compute retention curves across 12 months.
- Columns (inferred):
  - SubscriptionRetentionSnapshot: StartDate, EndDate, SubscriptionId
  - CustomerRetentionSnapshot: StartDate, EndDate, C360_ID
  - ResourceRetentionSnapshot: StartDate, EndDate, ResourceId
- Column Explain: Use dcount across Periods to compute Retain and join with cohort Total by StartMonth.

---

### Cached_ResourceFlow_Snapshot
- Priority: Normal
- What this table represents: Resource lifecycle flow at weekly/monthly partitions for a given ServiceType.
- Freshness expectations: Weekly and Monthly (Partition column).
- When to use / When to avoid:
  - Use: aggregate flow by Week/Month for SignalR or WebPubSub.
  - Avoid: raw resource-level join without understanding partitions.
- Columns (inferred from usage):
  - Date (datetime), ServiceType (string), Partition (string: 'Week' or 'Month'), plus flow attributes (not explicitly referenced).
- Column Explain: Extend Week/Month from Date then project-away metadata.

---

### Cached_CustomerFlow_Snapshot
- Priority: Normal
- What this table represents: Customer lifecycle flow at weekly/monthly partitions for a given ServiceType.
- Freshness expectations: Weekly and Monthly.
- Columns (inferred): Date, ServiceType, Partition; used similarly to resource flow.

---

### KPI_AWPS / OKRv2021_AWPS / OKRv2021_SocketIO / OKR_AWPS_SocketIO / KPI_SocketIO
- Priority: Normal
- What these represent: KPI/OKR time series for AWPS/WebPubSub and SocketIO sub-kind. Often pivoted by Category.
- Freshness expectations: Historical/periodic; augmented with goal series via inline datatables.
- Columns (inferred): Date (datetime), Category (string), Value (numeric); in OKR_AWPS_SocketIO also CustomerType.
- Column Explain: Use evaluate pivot to produce wide tables per Category.

---

### ResourceFlow_Weekly (function) / ResourceFlow_Monthly (function)
- Priority: Normal
- What these represent: Parameterized functions producing resource lifecycle aggregates by week/month. Queries specify startDate/endDate and service index (2 used for AWPS).
- Freshness expectations: Computed on-demand from underlying snapshots.
- Columns: flow metrics by Week/Month; details depend on function body.

---

### SubscriptionFlow_Weekly (function) / SubscriptionFlow_Monthly (function)
- Priority: High
- These are referenced as functions requiring parameters (startDate, endDate, service index). In practice, dashboards often use Cached_* snapshots instead to avoid parameter passing and reduce compute.
- Columns: Weekly/Monthly lifecycle metrics per subscription.

---

### OperationQoS_Daily
- Priority: Low
- What this table represents: Daily operational QoS per cloud role/resource (uptime/total time); supports SLA/SLO attainment.
- Freshness expectations: Daily; rolling 7/28-day calculations keyed off latest env_time.
- Common Filters: resourceId has 'microsoft.signalrservice/signalr' (or contains 'webpubsub' in AWPS section).
- Columns (inferred):
  - env_time (datetime), env_cloud_location (string as Region), env_cloud_role (string as ResourceId), totalUpTimeSec (numeric), totalTimeSec (numeric), resourceId (string)
- Column Explain: Compute Qos = sum(UpTime)/sum(TotalTime); region-level SlaAttainment via dcountif.

---

### ConnectivityQoS_Daily
- Priority: Low
- What this table represents: Daily connectivity QoS; similar to OperationQoS_Daily but with different attainment thresholds (0.995 vs 0.999).
- Freshness expectations: Daily; used with rolling windows.
- Columns: same shape as OperationQoS_Daily (env_* fields, totalUpTimeSec, totalTimeSec).

---

### ManageRPQosDaily
- Priority: Low
- What this table represents: Management-plane API QoS per API/region/day (Count by Result).
- Freshness expectations: Daily; used for rolling7/rolling28 and weekly/monthly summaries.
- Common Filters: ApiName exclusions (UNCATEGORY, INTERNAL…), CustomerType == 'SignalR' or 'WebPubSub'.
- Columns (inferred):
  - Date (datetime), ApiName (string), CustomerType (string), Region (string), Result (string), Count (long), SubscriptionId (string)
- Column Explain: QoS = sumif(Count, allowed results)/sum(Count).

---

### RuntimeRequestsGroups_Daily / RuntimeRequestsGroups_EU_Daily
- Priority: Low
- What these tables represent: Aggregated runtime request groups by Category and Metrics; filtered for meaningful volumes.
- Freshness expectations: Daily; last 60-day windows.
- Columns (inferred):
  - Date (datetime), Category (string, e.g., RestApiScenario/Transport), Metrics (string), RequestCount (long), ResourceId (string)
- Column Explain: Some Metrics normalized (e.g., v1→v1-HubProxy).

---

### RuntimeTransport_Daily / RuntimeTransport_EU_Daily
- Priority: Low
- What these tables represent: Transport breakdown by Framework-Transport combinations; used to build Category='Transport'.
- Freshness expectations: Daily; 60-day window.
- Columns (inferred):
  - Date (datetime), Framework (string), Transport (string), RequestCount (long), ResourceId (string)

---

### KPI_AWPS (table) / KPI_SocketIO (table)
- Priority: Normal
- KPI time series for AWPS and SocketIO; used directly in dashboards.
- Columns: not enumerated; treat similar to KPIv2019.

---

### Cached_SubsTotalWeekly_Snapshot (WebPubSub) / Cached_SubsTotalMonthly_Snapshot (WebPubSub)
- Priority: High
- Same shape as SignalR counterparts; ServiceType == 'WebPubSub'.
- Freshness expectations: Weekly/Monthly.

---

### Cached_Awps_TopCustomersWoW_v2_Snapshot
- Priority: Normal
- AWPS counterpart of top customers WoW deltas; used directly.
- Columns: similar to Asrs version but scoped to WebPubSub/AWPS.

---

### AwpsRuntimeRequestsGroups_Daily
- Priority: Low
- What this table represents: AWPS-specific runtime request groups; minor metrics normalization (v2021-*).
- Freshness expectations: Daily (60d window).
- Columns (inferred): Date, Category, Metrics, RequestCount, ResourceId.

---

### OKRv2021_AWPS / OKRv2021_SocketIO
- Priority: Normal
- See KPI/OKR section above; used with pivoting and union logic.

---

### DeleteSurvey / DeleteSurveyWebPubSub
- Priority: Normal
- What these tables represent: Survey feedback on deletions; minimal columns projected.
- Columns (from usage):
  - TIMESTAMP (datetime), Deployment (string), resourceId (string), reason (string), feedback (string)

---

### FeedbackSurvey / FeedbackSurveyWebPubSub
- Priority: Normal
- What these tables represent: Feedback survey results (CVA/CES values/comments) per service.
- Columns (from usage):
  - TimeStamp (datetime), CESValue (numeric), CVAValue (numeric), Comments (string); for WebPubSub an extra Type (string).

---

### OKR/Goal snapshots with “Dt” or updated goals (e.g., Cached_DtOKRARR_Snapshot, Cached_DtOKREstRevenueWeekly_Snapshot, Cached_DtOKREstRevenueMonthly_Snapshot, Cached_DtOKRSubsWeekly_Snapshot, Cached_DtOKRSubsMonthly_Snapshot)
- Priority: High
- What these represent: Similar to “Zn” snapshots but different scope/portfolio (“Dt”). Used with monthly window filters (startofmonth(now(), -35)).
- Columns: analogous to their Zn counterparts (TimeStamp/Week/Month; per-service metrics).

---

### Connection and live ratio cohort aggregations (constructed via joins)
- Priority: Normal
- Not standalone tables but patterns using BillingUsage_Daily joined to ResourceMetrics to derive HasConnection and LiveRatio (Swift/Occasional/Dedicate). Prefer using Cached_SubsTotal* snapshots which already represent these dims.

---

## Views (Reusable Layers)
Not applicable. No explicit database views were provided in the inputs. Parameterized Kusto functions (e.g., ResourceFlow_Weekly/Monthly, SubscriptionFlow_Weekly/Monthly) are referenced by queries but their bodies are not included here.

## Query Building Blocks (Copy-paste snippets)

- Time window template
  - Description: Choose a safe time window and bin. Avoid the current partial day/week/month. Optionally gate the end date based on sentinel regions to ensure complete ingestion.
  - Snippet:
    ```kusto
    // Parameters
    let LookbackDays = 60d;
    let UseGate = true;
    let SentinelRegions = dynamic(['australiaeast','westeurope']);

    // Effective end date (completeness gate)
    let EndDate =
        iif(UseGate,
            toscalar(
                BillingUsage_Daily
                | where Date > ago(10d) and Region in (SentinelRegions)
                | summarize RegionsReporting = dcount(Region) by Date
                | where RegionsReporting >= array_length(SentinelRegions)
                | top 1 by Date desc
                | project Date
            ),
            startofday(now()) - 1d // conservative fallback
        );

    // Daily window with bin
    BillingUsage_Daily
    | where Date > ago(LookbackDays) and Date <= EndDate
    | summarize Total = sum(Quantity) by Day = startofday(Date)
    ```

- Weekly/monthly cutoffs
  - Description: Exclude current week/month by capping upper bound at startofweek()/startofmonth().
  - Snippet:
    ```kusto
    // Weekly
    let WeekEnd = startofweek(now());
    someTable
    | where Date >= startofweek(now(), -12) and Date < WeekEnd
    | summarize ... by Week = startofweek(Date);

    // Monthly
    let MonthEnd = startofmonth(now());
    someTable
    | where Date >= startofmonth(now(), -12) and Date < MonthEnd
    | summarize ... by Month = startofmonth(Date);
    ```

- Join template (activity gating + enrichment)
  - Description: Gate on active usage with ResourceMetrics (MaxConnectionCount > 0) or presence in MaxConnectionCount_Daily; enrich with SubscriptionMappings.
  - Snippet:
    ```kusto
    let Active =
        ResourceMetrics
        | project Date, ResourceId, MaxConnectionCount
        | summarize HasConnection = max(MaxConnectionCount) > 0 by Date, ResourceId;

    BillingUsage_Daily
    | where Date >= ago(60d)
    | extend ResourceId = tolower(ResourceId)
    | join kind=inner Active on Date, ResourceId   // activity gate
    | parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
    | join kind=leftouter SubscriptionMappings on SubscriptionId  // enrich
    | project-away SubscriptionId1
    ```

- De-dup/latest-run pattern
  - Description: Pick the latest run per period (common in churn/convert tables).
  - Snippet:
    ```kusto
    // Latest run per Week
    ConvertCustomer_Weekly
    | order by Week asc, RunDay desc
    | extend Rank = row_number(1, prev(Week) != Week)
    | where Rank == 1
    ```

- Important filters
  - Description: Standard exclusions and service/SKU filters used across analyses.
  - Snippet:
    ```kusto
    // Internal exclusion and service type
    | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
    | where ResourceId has 'microsoft.signalrservice/signalr' // or '/webpubsub/'

    // SKU rules for revenue/consumption
    | where SKU in ('Free','Standard','Premium')
    // OR exclude message SKUs when computing revenue/consumption
    | where SKU !in ('MessageCount','MessageCountPremium')

    // Mgmt-plane tag noise
    ManageResourceTags
    | where ResourceId !has 'Microsoft.Authorization' and RequestName != 'Other'
    ```

- Important definitions
  - Revenue with placeholders:
    ```kusto
    extend Revenue = case(
        SKU == 'Free', <UnitPrice_Free>, 
        SKU == 'Standard', <UnitPrice_Standard>,
        SKU == 'Premium', <UnitPrice_Premium>,
        <UnitPrice_Default>
    ) * Quantity
    ```
  - UsageType segmentation:
    ```kusto
    extend UsageType = iif(CustomerType == 'Internal', 'Internal', BillingType)
    ```
  - Active and LiveRatio:
    ```kusto
    // Weekly
    | summarize Conn = max(MaxConnectionCount), ActiveDays = dcount(Date) by Week = startofweek(Date), ResourceId
    | extend HasConnection = Conn > 0,
             LiveRatio = case(ActiveDays < 3, 'Swift', 'Occasional')

    // Monthly
    | summarize ActiveDays = dcount(Date) by Month = startofmonth(Date), ResourceId
    | extend LiveRatio = case(ActiveDays < 3, 'Swift', ActiveDays < 10, 'Occasional', 'Dedicate')
    ```

- ID parsing/derivation
  - Description: Get SubscriptionId from ResourceId; normalize replicas.
  - Snippet:
    ```kusto
    | parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
    | extend ResourceId = tolower(ResourceId)
    | extend PrimaryResourceId = iif(ResourceId has '/replicas/', substring(ResourceId, 0, indexof(ResourceId, '/replicas/')), ResourceId)
    ```

- Sharded union (EU/global)
  - Description: Merge EU and non-EU shards, normalize fields first, then aggregate.
  - Snippet:
    ```kusto
    union isfuzzy=true
        FeatureTrackV2_Daily,
        FeatureTrackV2_EU_Daily
    | extend Date = startofday(Date), ResourceId = tolower(ResourceId)
    | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
    | summarize RequestCount = sum(RequestCount) by Week = startofweek(Date), Feature, Category
    ```

- ARR/Goal overlay pattern
  - Description: Join curated snapshot with inline goal series by TimeStamp/Date.
  - Snippet:
    ```kusto
    Cached_ZnOKRARR_Snapshot
    | join kind=fullouter (datatable(TimeStamp: datetime, SignalRGoal: real, SignalRGrowthGoal: real) [
        datetime(2024-01-31), 0.0, 0.0  // replace with real goals
    ]) on TimeStamp
    | extend TimeStamp = iif(isempty(TimeStamp), TimeStamp1, TimeStamp)
    | project-away TimeStamp1
    ```

- Completeness gate using two regions (copyable)
  - Description: Stabilize “latest” day across regions before slicing.
  - Snippet:
    ```kusto
    let EndDate = toscalar(
        BillingUsage_Daily
        | where Date > ago(10d) and Region in ('australiaeast','westeurope')
        | summarize counter = dcount(Region) by Date
        | where counter >= 2
        | top 1 by Date desc
        | project Date
    );
    ```

## Example Queries (with explanations)

1) ARR overlay with monthly goals
- Description: Overlays monthly ARR snapshot with inline goal/growth series. Uses fullouter join to preserve either side and aligns TimeStamp columns.
```kusto
Cached_ZnOKRARR_Snapshot
| join kind = fullouter (datatable(TimeStamp: datetime, SignalRGoal: real, SignalRGrowthGoal: real)[
datetime(2023-9-30), 22939552, 0.03085,
datetime(2023-10-31), 23647313, 0.03085,
datetime(2023-11-30), 24376911, 0.03085,
datetime(2023-12-31), 25129020, 0.03085,
datetime(2024-01-31), 25904333, 0.03085,
datetime(2024-02-29), 26703568, 0.03085,
datetime(2024-03-31), 27527462, 0.03085]) on TimeStamp
| extend TimeStamp = iif(isempty(TimeStamp), TimeStamp1, TimeStamp)
| project-away TimeStamp1
```

2) Revenue by service/SKU with activity gating and enrichment
- Description: Computes revenue per day/SKU with an activity gate (join to MaxConnectionCount_Daily), classifies service by ResourceId, then aggregates by CustomerType/Segment. Replace unit prices with placeholders before production use.
```kusto
let raw = BillingUsage_Daily
| where Date >= ago(30d) and SKU !in ('MessageCount', 'MessageCountPremium') and SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| extend Role = tolower(ResourceId)
| join kind = inner (MaxConnectionCount_Daily | where Date >= ago(60d) 
| project Date, Role = tolower(Role)) on Date, $left.Role == $right.Role
| extend isAsrs = ResourceId has 'microsoft.signalrservice/signalr', isAwps = ResourceId has 'microsoft.signalrservice/webpubsub',
Income = case(SKU == 'Free', <UnitPrice_Free>, SKU == 'Standard', <UnitPrice_Standard>, SKU == 'Premium', <UnitPrice_Premium>, <UnitPrice_Default>)*Quantity
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

3) Subscription totals with completeness-gated “current” reference
- Description: Builds monthly subscription counts split by service, with a sliding 28-day current period and historical month ends, gated by active usage (MaxConnectionCount_Daily). Useful when comparing current vs prior periods.
```kusto
let Current = toscalar(BillingUsage_Daily | top 1 by Date desc | project Date);
BillingUsage_Daily
| where Date > ago(60d)
| extend FakeKey = 1, IsSignalR = ResourceId has 'microsoft.signalrservice/signalr', IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub'
| summarize count() by Date, SubscriptionId, Current, IsSignalR,IsWebPubSub
| join kind = inner (MaxConnectionCount_Daily | where Date > ago(60d) | summarize count() by Date, SubscriptionId) on Date, SubscriptionId
| where datetime_diff('day', Current, Date) < 56
| extend TimeStamp = iif(datetime_diff('day', Current, Date) < 28, Current, Current - 1h)
| summarize count() by TimeStamp, SubscriptionId, IsSignalR, IsWebPubSub
| union (BillingUsage_Daily
| where Date >= datetime(20201201) and Date < startofmonth(Current)
| extend TimeStamp = startofday(endofmonth(Date)), IsSignalR = ResourceId has 'microsoft.signalrservice/signalr', IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub'
| summarize count() by TimeStamp, SubscriptionId, IsSignalR, IsWebPubSub
| join kind = inner (MaxConnectionCount_Daily 
| where Date >= datetime(20201201) and Date < startofmonth(Current)
| summarize count() by TimeStamp = startofday(endofmonth(Date)), SubscriptionId) on TimeStamp, SubscriptionId)
| summarize SubscriptionCnt = dcount(SubscriptionId, 4), SignalR = dcountif(SubscriptionId, IsSignalR, 4), WebPubSub = dcountif(SubscriptionId, IsWebPubSub, 4) by TimeStamp
```

4) AI cohort subscription trend with region-based completeness gate
- Description: Measures AI-related cohort counts (by keywords in ResourceId) over 28-day rolling windows, split by service, with goal overlay. Internal subscriptions are excluded.
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

5) Operational QoS with SLA attainment (SignalR)
- Description: Computes daily QoS and region-level SLA attainment for SignalR. Two-level summarize: first per resource to get UpTime/TotalTime; then region aggregate with dcountif(Qos >= threshold).
```kusto
let raw = OperationQoS_Daily
| where env_time > ago(43d) and resourceId has '/signalr/'
| summarize Qos = iif(sum(totalTimeSec) == 0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec)), UpTime = sum(totalUpTimeSec), TotalTime = sum(totalTimeSec) by Date = env_time, Region = env_cloud_location, ResourceId = env_cloud_role;
raw
| summarize TotalOperation = sum(TotalTime), Qos = iif(sum(TotalTime) == 0, 1.0, 1.0*sum(UpTime)/sum(TotalTime)), SlaAttainment = 1.0 * dcountif(ResourceId, Qos >=0.999, 4)/dcount(ResourceId, 4) by Date, Region
| union ( raw
| summarize TotalOperation = sum(TotalTime), Qos = iif(sum(TotalTime) == 0, 1.0, 1.0*sum(UpTime)/sum(TotalTime)), SlaAttainment = 1.0 * dcountif(ResourceId, Qos >=0.999, 4)/dcount(ResourceId, 4) by Date, Region = 'Overall')
```

6) Feature adoption (SignalR) with EU union and category normalization
- Description: Unions EU/global feature tracks, normalizes Date and Category, gates to active resources via BillingUsage_Daily (excluding message SKUs), and aggregates weekly.
```kusto
FeatureTrackV2_Daily 
    | union FeatureTrackV2_EU_Daily
    | where Date > startofweek(now()) - 56d 
    | project-away Properties
    | extend Date = startofday(Date), Category = case(Feature in ('BlazorServerSide', 'Samples'), Feature, Category endswith 'Ping', substring(Category, 8, indexof(Category, 'Ping') - 8), Category)
    | where ResourceId has 'microsoft.signalrservice/signalr' and SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
    | join kind = inner (BillingUsage_Daily | where SKU !in ('MessageCount', 'MessageCountPremium')) on Date, ResourceId
    | summarize RequestCount = sum(RequestCount), SKU = max(SKU) by Week = startofweek(Date), Feature, ResourceId, SubscriptionId, Category
```

7) AutoScale adoption in Premium (SignalR)
- Description: Counts resources with AutoScale feature signals and computes share among Premium resources per week.
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

8) Top subscriptions expansion by day (SignalR)
- Description: Expands curated top subscriptions to per-day metrics by joining ResourceMetrics and BillingUsage_Daily, and pivots into category-value pairs.
```kusto
let label = 'microsoft.signalrservice/signalr';
Cached_TopSubscriptions_Snapshot
| where Service == 'SignalR'
| project SubscriptionId
| join kind = inner (ResourceMetrics | where Date > startofday(now(), -29) and ResourceId has label
| parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
| summarize MaxConnectionCount = sum(MaxConnectionCount), MessageCount = sum(SumMessageCount) by Date, SubscriptionId) on SubscriptionId
| join kind = inner (BillingUsage_Daily | where Date > startofday(now(), -29) and ResourceId has label
| extend Revenue = case(SKU=='Standard', <UnitPrice_Standard>, SKU=='Premium', <UnitPrice_Premium>, SKU=='Free', <UnitPrice_Free>, <UnitPrice_Default>) * Quantity
| summarize Revenue = sum(Revenue), PaidUnits = sumif(Quantity, SKU in ('Standard', 'Premium')), ResourceCount = dcount(ResourceId) by Date, SubscriptionId) on SubscriptionId, Date
| extend Temp = pack('PaidUnits', PaidUnits, 'Revenue', Revenue, 'Messages', MessageCount, 'Connections', MaxConnectionCount, 'Resources', ResourceCount)
| mv-expand kind = array Temp
| project Date, SubscriptionId, Category = tostring(Temp[0]), Value = toreal(Temp[1])
```

## Reasoning Notes (only if uncertain)
- Timezone: Not specified; we assume UTC for all Date/env_time handling. This matches typical ADX behavior but should be validated against the ingestion sources.
- MaxConnectionCount_Daily: Referenced as a gating table but not listed in canonical tables. We treat it as an available fact or materialized view that exposes Role/Date; alternatively, use ResourceMetrics MaxConnectionCount > 0 for gating.
- Unit prices: Queries contain concrete numbers (1.61, 2.0). Per guidance, we abstract to <UnitPrice_Standard>/<UnitPrice_Premium>. If pricing differs by service/region/offer, the case statement should be extended.
- Internal exclusion macro: Both SignalRTeamInternalSubscriptionIds and SignalRTeamInternalSubscriptionIds() appear. We assume a function or set is available in the workspace; pick the one defined in your environment.
- Completeness gate: Sentinel regions 'australiaeast' and 'westeurope' are used as ingestion sentinels. If your product’s “complete” baseline differs, adjust the sentinel list and threshold.
- LiveRatio thresholds: Swift/Occasional/Dedicate cutoffs are inferred from queries (ActiveDays < 3; < 10). If business definitions evolve, centralize these thresholds in a let block.
- “AI customer” cohort: Implemented via ResourceId keyword search. Consider a curated allowlist or tag-based signal if precision is required.
- JOIN(OR)/JOIN(AND) tokens: Used in curated outputs to emit combined series. Preserve labels if consuming downstream visuals rely on them; otherwise, prefer explicit Service dimension.
- EU/non-EU unions: We observed FeatureTrackV2_* and Runtime*_* EU shards. If new shards exist (e.g., gov clouds), extend the union list to keep coverage consistent.