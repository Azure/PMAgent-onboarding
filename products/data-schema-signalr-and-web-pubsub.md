# SignalR and Web PubSub - Product and Data Overview Template

## 1. Product Overview

SignalR and Web PubSub provide real-time messaging services for web and application workloads. This product schema supports analytics for OKRs (ARR and AI customer growth), usage (revenue, connections, messages), service type growth across SignalR/Web PubSub/Socket.IO, feature tracking (replicas, auto-scale, Blazor Server, Aspire, Socket.IO), external/billable customers, and top customer insights. It prioritizes OKR, ARR/AI growth, usage, and feature adoption scenarios, with secondary coverage for QoS, management API, VS integration, and runtime request analyses.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**:
  SignalR and Web PubSub
- **Product Nick Names**: 
  [TODO]Data_Engineer: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations. Examples might include: ASRS, AWPS, WebPubSub, SocketIO, SignalR.
- **Kusto Cluster**:
  signalrinsights.eastus2
- **Kusto Database**:
  SignalRBI
- **Access Control**:
  [TODO] Data Engineer: If this product’s data has high confidentiality concerns, please specify the allowed groups/users here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

# SignalR and Web PubSub — Kusto Query Playbook

## Overview
Product: SignalR and Web PubSub

Summary: Power BI report queries for SignalR and Web PubSub covering OKR, ARR and AI customer growth, usage (revenue, connections, messages), service type growth (SignalR/WebPubSub/SocketIO), feature tracking (replicas, auto-scale, Blazor Server, Aspire, Socket.IO), external/billable customers, top customers, plus QoS, management API, VS integration and runtime request analyses.

Primary cluster/database:
- Cluster: signalrinsights.eastus2
- Database: SignalRBI

High-priority scenarios emphasized by users:
- OKR analysis, ARR and AI customer growth
- Usage analysis: Revenue, Connection count, Message count
- Service type growth: SignalR/Web PubSub/Web PubSub for SocketIO
- Feature tracking: replicas, auto-scales, Blazor Server, Aspire, Socket.IO
- External/Billable customers
- Top customers

Low-priority scenarios:
- VS (Visual Studio) integration
- QoS analysis
- RuntimeRequests

## Conventions & Assumptions

### Time semantics
Observed time columns
- Date (dominant across facts)
- env_time (QoS tables)
- TimeStamp (pre-aggregated snapshots)
- AdvancedServerTimestampUtc (Visual Studio telemetry)
- TIMESTAMP (ARM)
- Derived windows: Week = startofweek(Date), Month = startofmonth(Date), end-of-month markers via startofday(endofmonth(Date))

Canonical Time Column
- Use Date as the canonical time column.
- Alias other time columns to Date when joining:
  - project-rename patterns:
    - env_time → Date
    - AdvancedServerTimestampUtc → Date = startofday(AdvancedServerTimestampUtc)
    - TIMESTAMP → Date = startofday(TIMESTAMP)
    - TimeStamp often used as period end; keep as TimeStamp for OKR snapshots and alias to Month/Week only when explicitly needed.

Typical windows and binning
- Rolling: ago(30d), ago(60d), 28-day rolling “current” views.
- Weekly/monthly: startofweek(), startofmonth(), endofmonth().
- Avoid current day unless completeness is validated.

Timezone
- Not specified; assume UTC. Validate when comparing to business calendars.

### Freshness & Completeness Gates
- Ingestion cadence is not explicitly stated; treat current-day data as potentially incomplete.
- Use previous completed day or completed calendar week/month for stable reporting.
- Multi-slice completeness gate examples in queries:
  - Region-based gate (requires both australiaeast and westeurope reporting):
    - Compute EndDate = latest day where dcount(Region) across those regions ≥ 2; then bound facts Date <= EndDate.
  - “Current” derived from latest observed date in a source table; use that to anchor rolling windows (e.g., latest Date in BillingUsage_Daily or ResourceMetrics).
- Recommendation:
  - Daily: restrict to Date <= startofday(now()) - 1d unless a gate is in place.
  - Weekly/monthly: restrict to completed weeks/months or use pre-aggregated snapshots.

Pattern: completeness gate (region slices)
```kusto
let EndDate =
    toscalar(
        BillingUsage_Daily
        | where Date > ago(10d) and Region in ('australiaeast','westeurope')
        | summarize cnt = dcount(Region) by Date
        | where cnt >= 2
        | top 1 by Date desc
        | project Date
    );
... | where Date <= EndDate
```

### Joins & Alignment
Frequent keys
- SubscriptionId (string GUID)
- ResourceId (ARM ID string)
- CustomerId concepts:
  - CloudCustomerGuid (from SubscriptionMappings)
  - P360_ID/TPID (from CustomerModel)
- Region, SKU, Feature, Category, Kind

Join kinds
- leftouter (dimension enrichment: SubscriptionMappings, RPSettingLatest)
- inner (presence/active gating: MaxConnectionCount_Daily, ResourceMetrics)
- fullouter (joining OKR pre-aggregations with goal datatables)
- innerunique appears implicitly in some patterns (not explicitly used in provided queries)

Post-join hygiene
- Lower-case ResourceId prior to joins when mixing sources:
  - extend ResourceId = tolower(ResourceId)
- Normalize replicas:
  - if ResourceId contains ‘/replicas/’, use the primary ResourceId substring(…, 0, indexof('/replicas/'))
- Parse SubscriptionId from ResourceId when not present:
  - parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
- Project-away intermediate columns to avoid duplication.
- Resolve conflicting date columns (e.g., TimeStamp vs TimeStamp1) after fullouter join:
  - extend TimeStamp = iif(isempty(TimeStamp), TimeStamp1, TimeStamp); project-away TimeStamp1

### Filters & Idioms
- Exclude internal subscriptions: SubscriptionId !in (SignalRTeamInternalSubscriptionIds) or SignalRTeamInternalSubscriptionIds()
- Service scoping:
  - SignalR: ResourceId has 'microsoft.signalrservice/signalr'
  - Web PubSub: ResourceId has 'microsoft.signalrservice/webpubsub'
- SKU scoping:
  - Include: SKU in ('Free','Standard','Premium')
  - Exclude: SKU !in ('MessageCount','MessageCountPremium') for revenue/consumption views
- UsageType inference:
  - extend UsageType = iif(CustomerType == 'Internal', CustomerType, BillingType)
- Cohort allowlist example (AI):
  - ResourceId keyword set: 'gpt','ai','ml','cognitive','openai','chatgpt'
- dcount accuracy parameters:
  - dcount(..., 3 or 4) are used for higher accuracy in distinct counts.

### Cross-cluster/DB & Sharding
- EU/global same-schema shards:
  - FeatureTrackV2_Daily union FeatureTrackV2_EU_Daily
  - RuntimeRequestsGroups_Daily union RuntimeRequestsGroups_EU_Daily
  - RuntimeTransport_Daily union RuntimeTransport_EU_Daily
- Normalize time and keys before union; ensure matching column types.
- ARM/VS telemetry in other clusters:
  - ddtelinsights.WebTools_Raw
  - armprodgbl.eastus.{Requests, HttpIncomingRequests} via Unionizer('Requests','HttpIncomingRequests')
- Qualification pattern (if needed):
  - cluster('name').database('db').Table

Sharded union template
```kusto
let base =
    FeatureTrackV2_Daily
    | project Date, ResourceId, Feature, Category, RequestCount;
let eu =
    FeatureTrackV2_EU_Daily
    | project Date, ResourceId, Feature, Category, RequestCount;
union isfuzzy=true base, eu
| extend Date = startofday(Date)
| extend ResourceId = tolower(ResourceId)
```

### Table classes
- Fact (event/daily):
  - BillingUsage_Daily (usage quantities, revenue normalization)
  - ResourceMetrics (connections/messages activity)
  - MaxConnectionCount_Daily (presence gating)
  - ConnectionMode_Daily, FeatureTrack*_Daily, Manage*Daily, Runtime*Daily
- Snapshot:
  - RPSettingLatest, Cached_TopSubscriptions_Snapshot, Retention snapshots (Subscription/Customer/Resource)
- Pre-aggregated:
  - Cached_ZnOKR*_Snapshot, Cached_CuOKR*_Snapshot, Cached_SubsTotal*(Weekly/Monthly)_Snapshot, Cached_*_Flow_Snapshot, KPI tables

## Entity & Counting Rules (Core Definitions)

Entity model and keys
- Resource (key: ResourceId; normalized to primary when replicas present)
  → Subscription (key: SubscriptionId)
  → Customer (key: CloudCustomerGuid; enrich with CustomerModel)
  → Segment (key: SegmentName via SubscriptionMappings)
- Grouping levels
  - Day (Date), Week (startofweek(Date)), Month (startofmonth(Date)), and EOM snapshots (startofday(endofmonth(Date)))
  - Service scope: SignalR vs WebPubSub; Kind: SocketIO (RPSettingLatest)

Counting rules and definitions
- Active resource:
  - HasConnection if MaxConnectionCount > 0 (via ResourceMetrics), or presence in MaxConnectionCount_Daily for day gating.
- Paid units:
  - SKU in ('Standard','Premium'); MessageCount SKUs are excluded from revenue KPIs.
- Revenue normalization:
  - Map SKU to rates (use placeholders in new queries): Free → 0, Standard → <StandardRate>, Premium → <PremiumRate>
- UsageType:
  - Internal or BillingType derived from SubscriptionMappings
- Cohorts:
  - AI cohort defined by ResourceId keyword set ('gpt','ai','ml','cognitive','openai','chatgpt')
- Serverless/ServerMode:
  - From ConnectionMode_Daily (IsServerless if sum(ServerlessConnection) > 0; IsServerMode if sum(ProxyConnection) > 0)
  - From RPSettingLatest.ServiceMode for configured mode
- Replicas:
  - Replica ResourceIds identified by '/replicas/'; primary resource derived by trimming suffix
- Retention:
  - Cohort snapshots with StartDate/EndDate; compute Retain/Total by slicing RangeMonth/RangeWeek across windows
- Top customers:
  - Use Cached_TopSubscriptions_Snapshot as cohort seed; enrich from CustomerModel, FeatureTrack, RuntimeResourceTags, ConnectionMode, and daily facts

## Canonical Tables
Notes
- Primary cluster/database: signalrinsights.eastus2/SignalRBI.
- Timezone and refresh delay are unknown. Many tables are daily or weekly aggregates; avoid using current-day data unless you’ve validated backfill completion (typical practice: use startofday(now()) - 1d or restrict to completed calendar weeks/months).
- Common cross-cutting filters:
  - Exclude internal subscriptions: SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
  - Service scoping: ResourceId has 'microsoft.signalrservice/signalr' or ResourceId has 'microsoft.signalrservice/webpubsub'
  - Time windows: ago(30d), rolling 28d windows; weekly/monthly using startofweek()/startofmonth()
  - SKU scoping: SKU in ('Free','Standard','Premium'); often exclude MessageCount SKUs for revenue/consumption views

High Priority

### Table name: BillingUsage_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Daily fact table of billed usage at resource scope. Each row typically represents a resource-day-SKU quantity. Zero rows imply no reported usage for that dimension.
- Freshness expectations: Daily batch. Use completed days (e.g., Date <= startofday(now() - 1d)).
- When to use / When to avoid:
  - Use for revenue normalization, paid units, and SKU mix per day/week/month.
  - Use to derive customer/subscription/resource counts with SubscriptionMappings.
  - Use to segment by service type via ResourceId and SKU.
  - Avoid using alone to infer activity; combine with ResourceMetrics to confirm connections/messages.
- Similar tables & how to choose:
  - ResourceMetrics: activity (connections/messages); join with BillingUsage_Daily to get both quantity and activity.
  - MaxConnectionCount_Daily: used to guard for “active resources” on a given day when computing subscriber sets.
- Common Filters:
  - Date windows; exclude internal subs; SKU filters; ResourceId has '/signalr/' or '/webpubsub/'
- Table columns:
  | Column        | Type    | Description or meaning |
  |---------------|---------|------------------------|
  | Date          | datetime| Usage day (UTC unknown) |
  | SKU           | string  | Free/Standard/Premium, MessageCount variants sometimes excluded |
  | SubscriptionId| string  | Azure subscription GUID |
  | ResourceId    | string  | Full ARM resource ID; used to detect SignalR/WebPubSub and replicas |
  | Quantity      | real    | Daily usage unit count (normalized against SKU for revenue/consumption) |
  | Region        | string  | Azure region for the resource |
- Column Explain:
  - Date: partition and join key for calendar aggregation.
  - SKU: product tier; drives revenue normalization and paid unit logic.
  - SubscriptionId: used to exclude internal subscriptions and join to SubscriptionMappings.
  - ResourceId: service detection (SignalR/WebPubSub), replica collapsing, subscription extraction.
  - Quantity: core usage metric; convert to revenue via SKU mapping; to consumption via scaling.

### Table name: ResourceMetrics (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Daily resource telemetry aggregates: max connections, avg connections, message counts. Fact table for activity signals.
- Freshness expectations: Daily aggregates; use completed days/weeks.
- When to use / When to avoid:
  - Use to compute connections/messages per resource/subscription/time.
  - Use for “has activity” filters and live ratio classification with BillingUsage_Daily.
  - Avoid for revenue; join to BillingUsage_Daily for financial views.
- Similar tables & how to choose:
  - BillingUsage_Daily: financial/usage quantities; combine with ResourceMetrics for “quantity + activity”.
  - MaxConnectionCount_Daily: alternate source for presence gating in some queries.
- Common Filters:
  - Date windows; ResourceId has SignalR or WebPubSub labels; parse SubscriptionId from ResourceId; left joins to RPSettingLatest, SubscriptionMappings.
- Table columns:
  | Column            | Type     | Description or meaning |
  |-------------------|----------|------------------------|
  | Date              | datetime | Aggregation day |
  | ResourceId        | string   | ARM resource ID; sometimes normalized to primary resource for replicas |
  | MaxConnectionCount| long     | Daily max connections |
  | SumMessageCount   | long     | Daily total message count |
  | AvgConnectionCount| long     | Daily average connections |
  | Region            | string   | Azure region |
- Column Explain:
  - MaxConnectionCount/SumMessageCount: primary activity KPIs per day; often summed to weekly.
  - ResourceId: used for service scoping and replica collapsing.
  - Date: join axis to BillingUsage_Daily and snapshot weeks/months.

### Table name: SubscriptionMappings (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Dimension table mapping SubscriptionId to customer metadata for segmentation and billable/external classification.
- Freshness expectations: Updated as mappings change; treat as slowly changing; joins are leftouter.
- When to use / When to avoid:
  - Use for CustomerType (Internal vs External), BillingType, SegmentName, CloudCustomerGuid.
  - Use in top customers lists and customer/segment counts.
  - Avoid as a standalone fact; always join from usage/metrics.
- Similar tables & how to choose:
  - CustomerModel: subscription/customer enrichment for top customers; use when richer customer attributes are needed.
- Common Filters:
  - None; always leftouter-join on SubscriptionId after reducing fact tables.
- Table columns:
  | Column           | Type   | Description or meaning |
  |------------------|--------|------------------------|
  | SubscriptionId   | string | Join key to facts |
  | CustomerType     | string | Internal or External |
  | BillingType      | string | Billing category used in UsageType |
  | SegmentName      | string | Segment bucketing |
  | OfferName        | string | Commercial offer name |
  | OfferType        | string | Offer type |
  | CloudCustomerGuid| string | Customer identity for dedup |
  | TPID             | string | Partner/customer identifier used to build links |
- Column Explain:
  - CustomerType/BillingType: critical for Internal vs External segmentation and UsageType derivation.
  - SegmentName: used in OKR and growth slicing.
  - CloudCustomerGuid: used for customer-level dedup across subscriptions.

### Table name: RPSettingLatest (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Latest service configuration per resource (e.g., Kind, ServiceMode, extras like Aspire flags and Socket.IO).
- Freshness expectations: Snapshot-like; refreshed when configurations change.
- When to use / When to avoid:
  - Use to classify Default/Serverless/ServerMode, Kind (SignalR/WebPubSub/SocketIO), Aspire usage via Extras.
  - Avoid for counts alone; pair with ResourceMetrics/BillingUsage_Daily for activity/revenue.
- Similar tables & how to choose:
  - ConnectionMode_Daily: captures observed connection modes; RPSettingLatest expresses configured service mode.
- Common Filters:
  - ResourceId has SignalR/WebPubSub; project fields for joins to metrics/usage.
- Table columns:
  | Column     | Type   | Description or meaning |
  |------------|--------|------------------------|
  | ResourceId | string | ARM resource ID |
  | Kind       | string | Service kind (e.g., WebPubSub, SocketIO) |
  | ServiceMode| string | Configured mode; 'Default' when empty |
  | Extras     | string | JSON bag with flags (e.g., isAspire, socketIO.serviceMode) |
- Column Explain:
  - Kind/ServiceMode: key to split dashboards by feature/service type.
  - Extras: used by JSON extraction for Aspire and Socket.IO details.

### Table name: ConnectionMode_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Daily aggregates of connection modes by resource (serverless vs proxy/server mode).
- Freshness expectations: Daily; use completed days.
- When to use / When to avoid:
  - Use to derive IsServerless/IsServerMode flags per subscription/resource over a period.
  - Avoid as the only source of activity; combine with ResourceMetrics.
- Similar tables & how to choose:
  - RPSettingLatest for configured ServiceMode; this table shows observed connection volumes by mode.
- Common Filters:
  - Date windows; ResourceId has '/signalr/';
- Table columns:
  | Column             | Type     | Description or meaning |
  |--------------------|----------|------------------------|
  | Date               | datetime | Aggregation day |
  | ResourceId         | string   | ARM resource |
  | ServiceMode        | string   | Observed mode dimension |
  | ServerlessConnection| long    | Count of serverless connections |
  | ProxyConnection    | long     | Count of proxy/server-mode connections |
- Column Explain:
  - ServerlessConnection/ProxyConnection: summed to compute ConnectionCount and serverless/server-mode flags.

### Table name: FeatureTrack_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Daily feature usage counts at resource level (e.g., ServerSticky, ConnectionCountLimitReached, MultiEndpoints).
- Freshness expectations: Daily; ensure backfill before weekly rollups.
- When to use / When to avoid:
  - Use for feature adoption and needs-scale signals.
  - Use for top customers enrichment and health (e.g., upstream failures).
  - Avoid for revenue; join with usage tables as needed.
- Similar tables & how to choose:
  - FeatureTrackV2_Daily/EU variants: newer taxonomy, regionalized; prefer V2 where available.
- Common Filters:
  - Date windows; ResourceId filters; optional join to BillingUsage_Daily for SKU context.
- Table columns:
  | Column       | Type     | Description or meaning |
  |--------------|----------|------------------------|
  | Date         | datetime | Event day (startofday normalized in usage) |
  | ResourceId   | string   | ARM resource |
  | Feature      | string   | Feature key (e.g., ServerSticky, MultiEndpoints) |
  | RequestCount | long     | Occurrence count |
- Column Explain:
  - Feature: used in sumif() to derive per-feature counts or booleans (e.g., NeededScale).

### Table name: FeatureTrackV2_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: V2 daily feature tracking with Category and normalization (post-processing renames Ping categories).
- Freshness expectations: Daily; aligned across EU/global via union in queries.
- When to use / When to avoid:
  - Use for refined feature classification (Category, Feature).
  - Avoid mixing raw Category names; some renaming applied in queries.
- Similar tables & how to choose:
  - FeatureTrackV2_EU_Daily: EU shard; union both for full coverage.
  - FeatureTrack_Daily: legacy taxonomy.
- Common Filters:
  - Date windows; Feature in (...) subsets; ResourceId has service scope.
- Table columns:
  | Column     | Type     | Description or meaning |
  |------------|----------|------------------------|
  | Date       | datetime | Event day |
  | ResourceId | string   | ARM resource |
  | Feature    | string   | Feature key |
  | Category   | string   | Feature category (sometimes normalized) |
  | RequestCount| long    | Count |
- Column Explain:
  - Category/Feature: primary dimensions for feature adoption and signals.

### Table name: FeatureTrackV2_EU_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: EU-region shard of V2 feature tracking.
- Freshness expectations: Daily; union with global counterpart for completeness.
- When to use / When to avoid:
  - Use in union with FeatureTrackV2_Daily for worldwide views.
- Similar tables & how to choose:
  - FeatureTrackV2_Daily (global).
- Common Filters: Same as V2 global.
- Table columns: Same as FeatureTrackV2_Daily (observed).
- Column Explain: Same as above.

### Table name: FeatureTrack_AutoScale_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Daily records of AutoScale-related events per resource.
- Freshness expectations: Daily; used for weekly rollups and premium share.
- When to use / When to avoid:
  - Use to count resources with AutoScale activity and percent within Premium SKU.
  - Avoid deriving SKU from this table; join BillingUsage_Daily for SKU counts.
- Similar tables & how to choose:
  - FeatureTrack_Daily/V2 for broader feature signals.
- Common Filters:
  - Date windows; ResourceId has '/signalr/' or '/webpubsub/'; join weekly to BillingUsage_Daily.
- Table columns:
  | Column     | Type     | Description or meaning |
  |------------|----------|------------------------|
  | Date       | datetime | Day of event |
  | ResourceId | string   | ARM resource |
  | SubscriptionId| string| Subscription (used for internal exclusion) |
- Column Explain:
  - Presence of rows implies AutoScale usage; weekly dcount(ResourceId) is the core metric.

### Table name: RuntimeResourceTags_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Daily tags observed from runtime identifying app platform/proxy/static usage per subscription.
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use to annotate top customers (IsAppService, UseProxy, IsStaticApps).
  - Avoid using alone; join by SubscriptionId for enrichment.
- Similar tables & how to choose:
  - ManageResourceTags covers management-plane tagging, broader across providers.
- Common Filters:
  - Date > startofday(now(), -29); ServiceType in ('SignalR','WebPubSub').
- Table columns:
  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | Date          | datetime | Day |
  | ServiceType   | string   | 'SignalR' or 'WebPubSub' |
  | SubscriptionId| string   | Subscription |
  | IsAppService  | bool     | Using App Service |
  | IsProxy       | bool     | Proxy usage |
  | IsStaticApps  | bool     | Static Web Apps usage |
- Column Explain:
  - Flags are summarized by max() to shape per-subscription attributes.

### Table name: CustomerModel (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Enriched subscription/customer attributes and commercial KPIs for top customers experiences.
- Freshness expectations: Snapshot-like; updated with BI pipelines.
- When to use / When to avoid:
  - Use to project customer-facing fields: CloudCustomerName, P360 links, revenue/rate metrics.
  - Avoid using as standalone counts; dedup or join as needed.
- Similar tables & how to choose:
  - SubscriptionMappings overlaps on CustomerType/BillingType; CustomerModel is richer and tailored for top customer experiences.
- Common Filters:
  - None; inner-join from curated lists (Cached_TopSubscriptions_Snapshot).
- Table columns:
  | Column            | Type   | Description or meaning |
  |-------------------|--------|------------------------|
  | SubscriptionId    | string | Join key |
  | Revenue           | real   | Revenue KPI for subscription |
  | MaxConnection     | long   | Peak connections KPI |
  | MessageCount      | long   | Messages KPI |
  | Rate              | real   | Rate/score metric |
  | CloudCustomerName | string | Display name |
  | CustomerType      | string | Internal/External |
  | TPName            | string | Partner name |
  | BillingType       | string | Billing category |
  | OfferName         | string | Offer |
  | OfferType         | string | Offer type |
  | P360_ID           | string | Customer ID |
  | TPID              | string | Partner/customer identifier |
- Column Explain:
  - Revenue/MaxConnection/MessageCount: used for leaderboards/cards.
  - TPID/P360_ID: used to construct C360 links.

### Table name: Cached_TopSubscriptions_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Curated list of top subscriptions with retention windows (StartDate/EndDate) and service tag.
- Freshness expectations: Periodically refreshed snapshot; do not assume daily updates.
- When to use / When to avoid:
  - Use as entry set for “Top customers” pages, then enrich with metrics and features.
  - Avoid computing KPIs from this table alone; join metrics/usage tables by SubscriptionId and Date.
- Similar tables & how to choose:
  - CustomerModel for enrichment; ResourceMetrics/BillingUsage_Daily for KPI time series.
- Common Filters:
  - Service == 'SignalR' or 'WebPubSub'; recent window flags (IsNew, IsRetained).
- Table columns:
  | Column         | Type     | Description or meaning |
  |----------------|----------|------------------------|
  | Service        | string   | 'SignalR' or 'WebPubSub' |
  | SubscriptionId | string   | Subscription |
  | StartDate      | datetime | Window start |
  | EndDate        | datetime | Window end |
- Column Explain:
  - Service filters top N cohort per product; retention flags derive from StartDate/EndDate.

### Table name: Cached_ZnOKRARR_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Precomputed ARR OKR time series used for OKR visuals; joined with goal datatables by TimeStamp.
- Freshness expectations: Periodic; goal tables are static.
- When to use / When to avoid:
  - Use for ARR trend lines against targets.
  - Avoid mixing with raw billing without reconciliation.
- Similar tables & how to choose:
  - Cached_DtOKRARR_Snapshot for different segments (Dt vs Zn).
- Common Filters:
  - TimeStamp windows (monthly end-of-month stamps).
- Table columns:
  | Column    | Type     | Description or meaning |
  |-----------|----------|------------------------|
  | TimeStamp | datetime | Period end (monthly) |
  | …         | …        | ARR actual fields (unspecified in queries) |
- Column Explain:
  - TimeStamp is the join key to add goals; ensure fullouter join to preserve goal rows.

### Table name: Cached_ZnOKREstRevenueWeekly_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Weekly estimated revenue pre-aggregations for OKR. 
- Freshness expectations: Weekly; caution around current week partials.
- When to use / When to avoid:
  - Use for OKR visuals where pre-aggregated weekly revenue is expected.
  - Avoid mixing with daily BillingUsage unless normalizing to comparable windows.
- Similar tables & how to choose:
  - Cached_ZnOKREstRevenueMonthly_Snapshot for monthly.
- Common Filters: TimeStamp/week ranges.
- Table columns:
  | Column    | Type     | Description or meaning |
  |-----------|----------|------------------------|
  | TimeStamp | datetime | Week boundary |
  | …         | …        | Revenue fields (pre-agg) |
- Column Explain: Time alignment with goal series is required.

### Table name: Cached_ZnOKREstRevenueMonthly_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Monthly estimated revenue pre-aggregations for OKR.
- Freshness expectations: Monthly; after month close.
- When to use / When to avoid:
  - Use for OKR monthly bars/targets.
- Similar tables & how to choose:
  - Weekly variant for week views.
- Common Filters: Monthly TimeStamp windows.
- Table columns:
  | Column    | Type     | Description or meaning |
  |-----------|----------|------------------------|
  | TimeStamp | datetime | Month end |
  | …         | …        | Revenue fields |
- Column Explain: Designed to overlay with monthly goals.

### Table name: Cached_ZnOKRSubs_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: OKR subscription count time series (total and by service), used with goal overlays (e.g., WebPubSubGoal).
- Freshness expectations: Monthly; end-of-month TimeStamp.
- When to use / When to avoid:
  - Use for subscription growth OKR visuals (SignalR vs WebPubSub).
- Similar tables & how to choose:
  - Cached_ZnOKRSubsWeekly_Snapshot/Monthly_Snapshot (not listed here) for other cadences.
- Common Filters: TimeStamp windows.
- Table columns:
  | Column    | Type     | Description or meaning |
  |-----------|----------|------------------------|
  | TimeStamp | datetime | Month end |
  | …         | …        | Subscription metrics (unspecified) |
- Column Explain: Join with goal datatables for targets.

### Table name: Cached_CuOKRConsumption_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: OKR consumption time series (e.g., unit consumption totals) for cumulative/periodic views with goals.
- Freshness expectations: Periodic snapshots aligned with OKR cadence.
- When to use / When to avoid:
  - Use for consumption growth trajectories vs goals.
- Similar tables & how to choose:
  - Weekly/Monthly variants for specific cadences.
- Common Filters: TimeStamp windows.
- Table columns:
  | Column    | Type     | Description or meaning |
  |-----------|----------|------------------------|
  | TimeStamp | datetime | Period end |
  | …         | …        | Consumption metrics |
- Column Explain: Join with goal series by TimeStamp.

### Table name: Cached_CuOKRConsumptionWeekly_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Weekly consumption snapshots for OKR dashboards.
- Freshness expectations: Weekly, use completed weeks.
- When to use / When to avoid: Weekly views only.
- Similar tables: Monthly variant.
- Common Filters: Week ends.
- Table columns:
  | Column    | Type     | Description |
  |-----------|----------|-------------|
  | TimeStamp | datetime | Week end    |
  | …         | …        | Metrics     |
- Column Explain: Align with goal week series.

### Table name: Cached_CuOKRConsumptionMonthly_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Monthly consumption snapshots for OKR views.
- Freshness expectations: Month-end.
- When to use: Monthly OKR dashboards.
- Table columns:
  | Column    | Type     | Description |
  |-----------|----------|-------------|
  | TimeStamp | datetime | Month end   |
  | …         | …        | Metrics     |
- Column Explain: Use after month close for stability.

### Table name: OKR_AWPS_SocketIO (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: OKR series for Web PubSub Socket.IO scenarios, joined to goal series (SocketIOGoal/GrowthGoal).
- Freshness expectations: Periodic updates; not necessarily daily.
- When to use / When to avoid:
  - Use for Socket.IO growth tracking (External customers).
  - Avoid mixing internal/external unless filtered by CustomerType.
- Similar tables & how to choose:
  - OKRv2021_AWPS/OKRv2021_SocketIO for broader KPI sets (Normal priority).
- Common Filters:
  - Date >= datetime(20230820); CustomerType == 'External'
- Table columns:
  | Column       | Type     | Description or meaning |
  |--------------|----------|------------------------|
  | Date         | datetime | Period end date |
  | CustomerType | string   | Typically 'External' in OKR joins |
  | …            | …        | Socket.IO KPI fields |
- Column Explain:
  - Date used to fullouter join with goal series for trajectory comparisons.

Normal Priority

### Table name: OKRv2021 (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Historical KPI series with Category/Value pairs.
- Freshness expectations: Historical backfill; occasional updates.
- When to use: Pivot Category into KPI columns for trend lines.
- Similar tables: OKRv2021_AWPS, OKRv2021_SocketIO add service-specific KPIs.
- Common Filters: Date >= datetime(20200701)
- Table columns (observed): Date, Category, Value

### Table name: ManageResourceTags (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Management-plane operation tagging counts per request type.
- Use: Volume by RequestName/Tags; downstream resource/subscription counts.
- Columns (observed): Date, ResourceId, SubscriptionId, RequestName, Tags, Count

### Table name: KPIv2019 (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What: Historical KPI baseline.
- Use: Longitudinal KPI views; filter by Date.
- Columns: Date, … (metric columns)

### Table name: ChurnCustomers_Monthly (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What: Monthly churn counts by service type with ranking per run.
- Use: Standard/Overall churn rates at month level.
- Columns: Month, ServiceType, Standard, StandardChurn, Churn, Total, RunDay

### Table name: ConvertCustomer_Weekly (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What: Weekly conversion flows (Free→Paid, Standard→Premium).
- Use: Use latest run per week (row_number by Week).
- Columns: Week, FreeToPaid, FreeToStandard, FreeToPremium, StandardToPremium, RunDay, ServiceType

### Table name: SubscriptionRetentionSnapshot (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What: Subscription-level retention snapshot with StartDate/EndDate windows.
- Use: Cohort retention by months/weeks.
- Columns: StartDate, EndDate, SubscriptionId

### Table name: CustomerRetentionSnapshot (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What: Customer-level retention snapshot.
- Use: Cohort retention with C360_ID as key.
- Columns: StartDate, EndDate, C360_ID

### Table name: ResourceRetentionSnapshot (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What: Resource-level retention snapshot.
- Use: Cohort retention over resources.
- Columns: StartDate, EndDate, ResourceId

### Table name: Cached_ResourceFlow_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What: Precomputed resource flow (Week/Month partitions).
- Use: Use Partition == 'Week' or 'Month'; rename Date → Week/Month.
- Columns: Date, ServiceType, Partition, … (flow metrics)

### Table name: Cached_SubsTotalWeekly_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What: Weekly subscription totals snapshot.
- Use: Enrich with SubscriptionMappings; count by dimensions.
- Columns: Week, SubscriptionId, Region, OfferType, OfferName, BillingType, SKU, CustomerType, HasConnection, LiveRatio, CloudCustomerGuid/SegmentName (via join)

### Table name: Cached_SubsTotalMonthly_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What: Monthly subscription totals snapshot.
- Use: Same as weekly, but month-grained.
- Columns: Month, SubscriptionId, Region, Offer..., BillingType, SKU, CustomerType, HasConnection, LiveRatio

### Table name: Cached_CustomerFlow_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What: Precomputed customer flow (Week/Month).
- Use: Partition to Week/Month; customer cohort movements.
- Columns: Date, ServiceType, Partition, … (customer flow metrics)

### Table name: KPI_AWPS (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What: KPI set for AWPS (Web PubSub); referenced as scalar source.
- Columns: … (KPI fields)

### Table name: DeleteSurvey (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What: SignalR delete survey feedback telemetry.
- Use: Basic projection for feedback analysis.
- Columns: TIMESTAMP, Deployment, resourceId, reason, feedback

### Table name: FeedbackSurvey (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What: SignalR feedback surveys.
- Use: CES/CVA and comments by time.
- Columns: TimeStamp, CESValue, CVAValue, Comments

### Table name: DeleteSurveyWebPubSub (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What: Web PubSub delete survey telemetry.
- Columns: TIMESTAMP, Deployment, resourceId, reason, feedback

### Table name: ResourceFlow_Weekly (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What: Function/materialized flow used via function calls; referenced for WebPubSub time ranges.
- Columns: Week, … (flow metrics)

### Table name: ResourceFlow_Monthly (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What: Monthly resource flow (function-backed).
- Columns: Month, … (flow metrics)

### Table name: SubscriptionFlow_Weekly (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What: Weekly subscription flow (function-backed).
- Columns: Week, … 

### Table name: SubscriptionFlow_Monthly (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What: Monthly subscription flow (function-backed).
- Columns: Month, … 

### Table name: CustomerFlow_Weekly (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What: Weekly customer flow (function-backed).
- Columns: Week, …

### Table name: CustomerFlow_Monthly (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What: Monthly customer flow (function-backed).
- Columns: Month, …

### Table name: OKRv2021_AWPS (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What: AWPS-specific OKR KPI series.
- Use: Union with OKRv2021_SocketIO; pivot(Category) for charting.
- Columns: Date, Category, Value

### Table name: OKRv2021_SocketIO (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What: Socket.IO-specific OKR KPI series.
- Use: Namespaced categories (e.g., 'SocketIO…').
- Columns: Date, Category, Value

Low Priority

### Table name: OperationQoS_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Low
- What: Operation-layer QoS uptime with env_* fields (cloud_location, role).
- Use: SLA attainment per region/resource; rolling 7/28-day windows.
- Columns: env_time, env_cloud_location, env_cloud_role, totalTimeSec, totalUpTimeSec, resourceId

### Table name: ConnectivityQoS_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Low
- What: Connectivity-layer QoS uptime (similar to OperationQoS).
- Use: SLA at 99.5% threshold typical in queries.
- Columns: env_time, env_cloud_location, env_cloud_role, totalTimeSec, totalUpTimeSec, resourceId

### Table name: ManageRPQosDaily (signalrinsights.eastus2/SignalRBI)
- Priority: Low
- What: Management RP QoS per APIName/Result.
- Use: QoS as success-style ratios; filter out UNCATEGORY/internal.
- Columns: Date, Region, ApiName, Result, Count, CustomerType, SubscriptionId

### Table name: RuntimeRequestsGroups_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Low
- What: Grouped runtime request stats (non-Transport).
- Use: Threshold filters on ResourceCount/RequestCount; category/metrics normalization.
- Columns: Date, Category, Metrics, ResourceCount, RequestCount

### Table name: RuntimeRequestsGroups_EU_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Low
- What: EU shard of grouped runtime requests.
- Columns: Same as global

### Table name: RuntimeTransport_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Low
- What: Transport-level runtime stats.
- Use: Combine Framework and Transport into Metrics.
- Columns: Date, Framework, Transport, RequestCount, ResourceId

### Table name: RuntimeTransport_EU_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Low
- What: EU shard transport stats.
- Columns: Same as global

### Table name: WebTools_Raw (cluster: ddtelinsights)
- Priority: Low
- What: Visual Studio telemetry events (server dependencies, provisioning, publish) relevant to SignalR detection and provisioning flows.
- Use: Dev/project counts, ratios, SKU selections.
- Columns: AdvancedServerTimestampUtc, EventName, Properties (dynamic), Measures (dynamic), ExeVersion, MacAddressHash, ActiveProjectId

### Table name: Requests (cluster: armprodgbl.eastus)
- Priority: Low
- What: ARM Requests telemetry used via Unionizer().
- Use: EventGrid filter PUT/DELETE tracking; targetUri parsing.
- Columns: TIMESTAMP, targetResourceProvider, httpMethod, targetResourceType, targetUri, subscriptionId, SourceNamespace

### Table name: HttpIncomingRequests (cluster: armprodgbl.eastus)
- Priority: Low
- What: ARM HTTP incoming requests; paired with Requests in Unionizer().
- Use: Same filtering for SIGNALRSERVICE EventGrid filters.
- Columns: TIMESTAMP, … (HTTP fields aligned with Unionizer)

### Table name: AwpsRuntimeRequestsGroups_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Low
- What: AWPS-specific runtime grouped requests with Metrics normalization.
- Columns: Date, Category, Metrics, …

Schema and column completeness
- Full schemas were inferred from query usage. For authoritative, complete schemas, run in ADX:
  - <cluster("signalrinsights.eastus2").database("SignalRBI").BillingUsage_Daily> | getschema
  - Replace table names and clusters accordingly; for cross-cluster tables (e.g., ddtelinsights, armprodgbl.eastus), specify the correct database and run getschema.
- If unions across EU/global shards are required, ensure consistent column types before union (explicit casts if needed).

## Views (Reusable Layers)
No reusable views/functions were defined in the input. Some reports reference pre-aggregated “Cached_*_Snapshot” tables or function-like names (e.g., ResourceFlow_Weekly, SubscriptionFlow_Weekly); treat those as curated tables/functions rather than views.

## Query Building Blocks (Copy-paste snippets)

- Time window template (daily with effective end gate)
  - Use when you need consistent daily windows across shards (e.g., AU/EU) and want to avoid partial days.
```kusto
// Parameters
let RegionsForGate = dynamic(['australiaeast','westeurope']);
let LookbackDays = 60d;
// End gate day where all required slices reported
let EndDate =
    toscalar(
        BillingUsage_Daily
        | where Date > ago(10d) and Region in (RegionsForGate)
        | summarize cnt = dcount(Region) by Date
        | where cnt >= array_length(RegionsForGate)
        | top 1 by Date desc
        | project Date
    );
BillingUsage_Daily
| where Date >= ago(LookbackDays) and Date <= EndDate
```

- Time window template (weekly/monthly completed periods)
  - Use for stable weekly/monthly reporting without partial current period.
```kusto
// Completed weeks/months
let EndWeek = startofweek(now()) - 1d;
let EndMonth = startofmonth(now());
FactTable
| where Date >= startofweek(now(), -12) and Date < startofweek(now())
// or
| where Date >= startofmonth(now(), -12) and Date < startofmonth(now())
```

- Join template: enrich facts with subscription metadata and align ResourceId
  - Use when adding CustomerType/BillingType/SegmentName and/or RP settings.
```kusto
// Align ResourceId and parse SubscriptionId if needed
Fact
| extend ResourceId = tolower(ResourceId)
| parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
| join kind=leftouter SubscriptionMappings on SubscriptionId
| join kind=leftouter (RPSettingLatest | extend ResourceId = tolower(ResourceId)) on ResourceId
```

- De-dup and “latest per entity”
  - Use to get the latest day’s record per ResourceId or per cohort.
```kusto
Fact
| summarize arg_max(Date, *) by ResourceId
```

- Distinct counts with accuracy and activity gates
  - Use to compute totals and active subsets.
```kusto
// Active by connections
ResourceMetrics
| summarize HasConnection = max(MaxConnectionCount) > 0 by Date, ResourceId
| join kind=inner (BillingUsage_Daily | project Date, ResourceId, SubscriptionId, SKU) on Date, ResourceId
| summarize
    ResourceTotal = dcount(ResourceId, 3),
    ActiveResourceTotal = dcountif(ResourceId, HasConnection, 3),
    SubscriptionTotal = dcount(SubscriptionId, 3)
  by Date
```

- Important filters
  - Exclude internal and MessageCount SKUs; scope to service.
```kusto
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| where ResourceId has 'microsoft.signalrservice/signalr' // or '.../webpubsub'
| where SKU in ('Free','Standard','Premium') // or SKU !in ('MessageCount','MessageCountPremium')
```

- Revenue normalization (use placeholders)
  - Use to compute estimated revenue from quantity. Replace rates appropriately.
```kusto
| extend Revenue =
    case(
        SKU == 'Free', 0.0,
        SKU == 'Standard', <StandardRate>,
        SKU == 'Premium', <PremiumRate>,
        <FallbackRate>
    ) * Quantity
```

- AI cohort construction (allowlist)
  - Use to restrict to AI-related resources by name conventions.
```kusto
| where ResourceId has 'gpt' or ResourceId has 'ai' or ResourceId has 'ml'
   or ResourceId has 'cognitive' or ResourceId contains 'openai' or ResourceId contains 'chatgpt'
```

- ID parsing/derivation and replica normalization
  - Use when replica suffixes exist and you need the primary resource grouping.
```kusto
| extend ResourceId = tolower(ResourceId)
| extend IsReplica = ResourceId has '/replicas/'
| extend PrimaryResourceId = iif(IsReplica, substring(ResourceId, 0, indexof(ResourceId, '/replicas/')), ResourceId)
| parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
```

- Sharded union (EU + Global)
  - Use to merge regional shards before summarization.
```kusto
let global = RuntimeRequestsGroups_Daily | project Date, Category, Metrics, ResourceCount, RequestCount;
let eu     = RuntimeRequestsGroups_EU_Daily | project Date, Category, Metrics, ResourceCount, RequestCount;
union isfuzzy=true global, eu
| extend Date = startofday(Date)
| summarize ResourceCount = sum(ResourceCount), RequestCount = sum(RequestCount) by Date, Category, Metrics
```

- Rolling window QoS snapshot
  - Use latest day as the “as-of” anchor; compute 7/28-day rolling uptime.
```kusto
let anchor = toscalar(OperationQoS_Daily | top 1 by env_time desc | project env_time);
OperationQoS_Daily
| where env_time > anchor - 7d and resourceId has 'microsoft.signalrservice/signalr'
| summarize Qos = iif(sum(totalTimeSec) == 0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec))
| project Date = anchor, Type = 'Rolling7', Qos
```

## Example Queries (with explanations)

1) Revenue by Service and SKU (SignalR vs Web PubSub) — daily
- Intent: Compute Income (estimated revenue) by day, SKU, and split between SignalR and WebPubSub after gating with MaxConnectionCount_Daily. Excludes internal subscriptions and MessageCount SKUs. Joins SubscriptionMappings to segment by CustomerType and SegmentName. Demonstrates pack/mv-expand reshaping to long format.
- Adaptation: Adjust ago(30d/60d), replace revenue rates with updated ones, or change groupings (e.g., add Region).
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

2) Consumption by Service and SKU (SignalR vs Web PubSub) — daily
- Intent: Similar to revenue, but uses Consumption = sum(Quantity) * 24 (domain-specific normalization) and splits by service. Excludes internal subs and MessageCount SKUs, gates via MaxConnectionCount_Daily.
- Adaptation: Change time window, normalization factor, or segmentation fields.
```kusto
let raw = BillingUsage_Daily
| where Date >= ago(30d) and SKU !in ('MessageCount', 'MessageCountPremium') and SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
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

3) OKR Subscriptions with Monthly Goals (WebPubSubGoal) — fullouter on goals
- Intent: Combine pre-aggregated monthly OKR subscription snapshot with a goal datatable; preserves both sides with fullouter and aligns TimeStamp.
- Adaptation: Replace goal series, adjust window via startofmonth(now(), -N).
```kusto
Cached_ZnOKRSubs_Snapshot
| join kind = fullouter (datatable(TimeStamp: datetime, WebPubSubGoal: real, WebPubSubGrowthGoal: real)[
    datetime(2024-09-30), 4450, 0.035938037,
    datetime(2024-10-31), 4610, 0.035938037,
    datetime(2024-11-30), 4776, 0.035938037,
    datetime(2024-12-31), 4947, 0.035938037,
    datetime(2025-01-31), 5125, 0.035938037,
    datetime(2025-02-28), 5309, 0.035938037,
    datetime(2025-03-31), 5500, 0.035938037
]) on TimeStamp
| extend TimeStamp = iif(isempty(TimeStamp), TimeStamp1, TimeStamp)
| project-away TimeStamp1
| where TimeStamp >= startofmonth(now(), -35)
```

4) AI Cohort Subscription Growth — 28-day rolling and historical monthly
- Intent: Build an AI cohort (ResourceId keyword filter), compute current and prior 28-day windows, plus historical month-end subscription counts by SignalR/WebPubSub, then overlay monthly goals.
- Adaptation: Change keywords, window size (DoM), or replace goals.
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

5) Weekly LiveRatio and Active Resources (SignalR)
- Intent: Join usage and metrics to classify LiveRatio (Swift/Occasional by ActiveDays) and HasConnection via MaxConnectionCount; compute weekly distinct resources by Region and SKU.
- Adaptation: Expand LiveRatio bands; change weeks lookback; adjust service scope.
```kusto
BillingUsage_Daily
    | where Date >= startofweek(now(), -8) and SubscriptionId !in (SignalRTeamInternalSubscriptionIds()) and ResourceId has 'microsoft.signalrservice/signalr'
    | join kind = inner ResourceMetrics on ResourceId, Date
    | summarize Conn = max(MaxConnectionCount), SKU = max(SKU), Region = max(Region), ActiveDays = dcount(Date) by Week=startofweek(Date), ResourceId
    | project Week, ResourceId, Category = 'Total', Region, SKU, HasConnection = Conn > 0, LiveRatio = case(ActiveDays < 3, 'Swift', 'Occasional')
    | summarize ResourceCnt = dcount(ResourceId, 3) by Week, Category, Region, SKU, HasConnection, LiveRatio
```

6) QoS Rolling Windows (SignalR Operations QoS)
- Intent: Compute 7-day and 28-day rolling QoS anchored at the latest day available in OperationQoS_Daily.
- Adaptation: Change threshold, resourceId filter (SignalR vs WebPubSub), or window lengths.
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

7) AutoScale Adoption in Premium (SignalR)
- Intent: Measure the share of resources using AutoScale among Premium resources per week.
- Adaptation: Switch to WebPubSub service scope; alter lookback or gating for internal subs.
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

8) Top Subscriptions — Enriched Customer Card (SignalR)
- Intent: Start from a curated top subscriptions snapshot; enrich with CustomerModel, runtime tags, feature signals, and connection mode flags to produce a rich profile per subscription.
- Adaptation: Change service to 'WebPubSub'; adjust enrichment joins or time window.
```kusto
Cached_TopSubscriptions_Snapshot
| where Service == 'SignalR'
| extend IsNew = StartDate > startofday(now(), -29), IsRetained = EndDate >= startofday(now(), -3)
| join kind = inner CustomerModel on SubscriptionId
| project SubscriptionId, Revenue, MaxConnection, Messages=MessageCount, Rate, CloudCustomerName, CustomerType, TPName, BillingType, OfferName, OfferType, P360_ID, IsRetained, IsNew,
C360Url = strcat('https://cxp.azure.com/cxobserve/customers/ch:customer::tpid:',TPID,'/summary')
| join kind = leftouter (RuntimeResourceTags_Daily | where Date > startofday(now(), -29) and ServiceType == 'SignalR'
| summarize IsAppService = max(IsAppService), UseProxy = max(IsProxy), IsStaticApps = max(IsStaticApps) by SubscriptionId) on SubscriptionId
| join kind = leftouter (FeatureTrack_Daily | where Date > startofday(now(), -29) and ResourceId has '/signalr/'
| extend SubscriptionId = tostring(split(ResourceId, '/')[2])
| summarize ServerSticky = sumif(RequestCount, Feature == 'ServerSticky'), NeededScale = sumif(RequestCount, Feature == 'ConnectionCountLimitReached'),
MultiEndpoints = sumif(RequestCount, Feature == 'MultiEndpoints') by SubscriptionId) on SubscriptionId
| extend ServerSticky = ServerSticky > 0, NeededScale = NeededScale > 0, MultiEndpoints = MultiEndpoints > 0
| join kind = leftouter (ConnectionMode_Daily | where Date > startofday(now(), -29) and ResourceId has '/signalr/'
| extend SubscriptionId = tostring(split(ResourceId, '/')[2])
| summarize IsServerless = sum(ServerlessConnection) > 0, IsServerMode = sum(ProxyConnection) > 0 by SubscriptionId) on SubscriptionId
| project-away SubscriptionId1, SubscriptionId2, SubscriptionId3
```

9) Socket.IO Weekly Counts (Web PubSub)
- Intent: For Web PubSub Kind = SocketIO resources, count resources and connections by week and SKU; demonstrates joining RPSettingLatest with usage and metrics, excluding internal subs.
- Adaptation: Alter Kind or add ServiceMode breakdown.
```kusto
RPSettingLatest
| where Kind == 'SocketIO'
| join kind = inner (BillingUsage_Daily | where Date >= startofweek(now(), -12) and SKU in ('Free', 'Standard', 'Premium')) on ResourceId
| join kind = inner (ResourceMetrics | where Date >= startofweek(now(), -12)) on ResourceId
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| summarize SKU = max(SKU1), MaxConn = max(MaxConnectionCount) by Week = startofweek(Date), ResourceId
| summarize ResourceCnt = dcount(ResourceId), ConnectionCnt = sum(MaxConn) by Week, SKU
```

10) Web PubSub Estimated Revenue (with completeness gate)
- Intent: Compute Total paid units and Revenue for Web PubSub, excluding internal subs, bounded by EndDate gate across key regions.
- Adaptation: Adjust regions or include MessageCount logic differently.
```kusto
let EndDate = toscalar(BillingUsage_Daily | where Date > ago(5d) and Region in ('australiaeast', 'westeurope') 
| summarize counter = dcount(Region) by Date | where counter >= 2 | top 1 by Date desc | project Date);
BillingUsage_Daily
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds()) and Date >= ago(60d) and ResourceId has '/webpubsub/' and Date >= datetime(20210426) and Date <= EndDate
| extend Revenue = case(SKU == 'Free', 0.0, SKU == 'Standard', 1.61, SKU == 'Premium', 2.0, 1.0)*Quantity
| join kind = leftouter SubscriptionMappings on SubscriptionId
| summarize Total = sumif(Quantity, SKU in ('Standard', 'Premium')), Revenue = sum(Revenue) by Date, SKU, CustomerType
```

## Reasoning Notes (only if uncertain)
- Timezone is unknown; we assume UTC based on typical ADX practice. If business calendars require local time, adjust with datetime_add for alignment.
- Current-day completeness is not guaranteed. Queries frequently avoid current day or compute EndDate gates from multi-region presence; we adopt the same pattern for reliability.
- SignalRTeamInternalSubscriptionIds appears both as a function call and a value list in queries. Treat it as a function where available; otherwise, expect a defined list/function in the environment.
- Revenue rate mapping uses specific constants in examples (e.g., 1.61, 2.0). For new analyses, parameterize rates (<StandardRate>/<PremiumRate>) and source them from a maintained lookup to avoid hardcoding.
- “LiveRatio” bands are inferred heuristics (e.g., ActiveDays < 3 → Swift). If used for OKRs, formalize the thresholds in a shared definition.
- Replica normalization is used in some metrics (trim ‘/replicas/’); where not applied, counts can double-count replicas. Prefer normalizing for resource-level reporting unless replica-level views are explicitly required.
- EU/global sharded tables (FeatureTrackV2, Runtime* tables) must be unioned for complete coverage. Ensure column types match; explicit casts may be needed if schema drifts.