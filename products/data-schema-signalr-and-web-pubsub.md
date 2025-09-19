# SignalR and Web PubSub - Product and Data Overview Template

## 1. Product Overview

SignalR and Web PubSub are Azure managed real-time messaging services enabling publish/subscribe, WebSocket-based communication, and serverless integration patterns. This schema aims to support OKR and ARR analysis, usage and revenue tracking, customer growth, feature adoption (e.g., replicas, autoscale, Blazor Server), segmentation across service types (SignalR, Web PubSub, Web PubSub for Socket.IO), and top customer insights.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**:
SignalR and Web PubSub
- **Product Nick Names**: 
**[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations.
- **Kusto Cluster**:
signalrinsights.eastus2
- **Kusto Database**:
SignalRBI
- **Access Control**:
**[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed **groups/users** here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

## Build a Kusto Query Playbook: SignalR and Web PubSub

## Overview
- Product: SignalR and Web PubSub
- Summary: Tables/Scenarios that are most important: OKR analysis, ARR and AI customer growth; Usage analysis: Revenue, Connection count, Message count; Different service type growth: SignalR/Web PubSub/Web PubSub for SocketIO; Feature tracks (replicas, auto-scales, blazor-server, etc.); External customer and Billable customers; Top customers. Low priority and rarely used scenarios: VS (Visual Studio) integration; QoS analysis; RuntimeRequests.
- Primary cluster and database: signalrinsights.eastus2 / SignalRBI
  - Alternates noted in queries: armprodgbl.eastus (ARM analytics Unionizer), ddtelinsights (DevTools)

## Conventions & Assumptions

### Time semantics
- Observed timestamp columns:
  - Date (most fact and feature tables)
  - TimeStamp/TimeStamp1 (snapshots and goal joins)
  - env_time (QoS, operational telemetry)
  - TIMESTAMP (ARM Unionizer)
  - AdvancedServerTimestampUtc (DevTools/WebTools telemetry)
  - StartDate/EndDate (retention snapshots, top lists inclusion windows)
- Canonical Time Column: Date
  - Alias patterns:
    - QoS tables: project-rename Date = env_time
      - Example: OperationQoS_Daily | project-rename Date = env_time
    - Snapshots: project-rename Date = TimeStamp or align to Month/Week
      - Example: Some queries extend Month = startofmonth(Date) or Week = startofweek(Date)
    - ARM: project Date = startofday(TIMESTAMP)
    - DevTools: project Date = startofday(AdvancedServerTimestampUtc) or startofweek(...)
- Typical windows and bin() resolutions:
  - Rolling days: ago(30d), ago(43d), ago(60d), ago(61d)
  - Weeks: startofweek(now(), -8 | -10 | -12 | -26)
  - Months: startofmonth(now(), -12 | -16)
  - Common bins: startofweek(Date), startofmonth(Date), startofday(Date)
- Timezone:
  - Not specified. Assume UTC unless otherwise noted. Avoid using current day without a completeness gate.

### Freshness & Completeness Gates
- Ingestion cadence and current-day completeness: unknown. Treat current day as potentially incomplete.
- Effective end date pattern (multi-slice gate):
  - Find the last day where ≥2 sentinel regions report data (Australia East and West Europe) and use it as the effective end date.
  - Example gate:
    ```kusto
    let EffectiveEndDate =
      toscalar(
        BillingUsage_Daily
        | where Date > ago(10d) and Region in ('australiaeast','westeurope')
        | summarize regions = dcount(Region) by Date
        | where regions >= 2
        | top 1 by Date desc
        | project Date
      );
    ```
  - Then filter facts: | where Date <= EffectiveEndDate
- Closed periods:
  - For weekly/monthly analyses, prefer last full week/month:
    - Date >= datetime_add('week', -N, startofweek(Current)) and Date < startofweek(Current)
    - Date >= startofmonth(Current, -N) and Date < startofmonth(Current)

### Joins & Alignment
- Frequent keys:
  - ResourceId (string)
  - SubscriptionId (GUID string)
  - CloudCustomerGuid (customer)
  - Region, SKU
- Parsing and normalization:
  - Extract SubscriptionId from ResourceId:
    - parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
    - or extend SubscriptionId = tostring(split(ResourceId, '/')[2])
  - Lowercase ResourceId before joins:
    - extend ResourceId = tolower(ResourceId)
  - Handle replicas:
    - PrimaryResource = iif(ResourceId has '/replicas/', substring(ResourceId, 0, indexof(ResourceId, '/replicas/')), '')
- Typical join kinds:
  - inner to enforce activity/completeness gates (e.g., join to MaxConnectionCount_Daily or curated ApiName list)
  - leftouter for enrichment (SubscriptionMappings, RPSettingLatest)
- Post-join hygiene:
  - Resolve duplicate columns: coalesce() or rename Projected columns like SKU1 → SKU, and project-away duplicates.
  - Drop temporary columns and keys: project-away <temp columns>.

### Filters & Idioms
- Internal exclusion:
  - Always exclude internal/team subs: SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
- Product segmentation via ResourceId:
  - SignalR: ResourceId has 'microsoft.signalrservice/signalr'
  - Web PubSub: ResourceId has 'microsoft.signalrservice/webpubsub' or contains '/webpubsub/'
- SKU rules:
  - Primary SKUs: 'Free','Standard','Premium'
  - Often exclude 'MessageCount' SKUs when computing revenue/consumption or top metrics
- UsageType derivation:
  - UsageType = iif(CustomerType == 'Internal', CustomerType, BillingType)
- Cohorts:
  - AI cohort (example):
    - ResourceId has one of: 'gpt','ai','ml','cognitive' or contains 'openai','chatgpt'
- ARM operations (Unionizer):
  - targetResourceProvider == 'MICROSOFT.SIGNALRSERVICE', httpMethod in ('PUT','DELETE'), targetResourceType == 'SIGNALR/EVENTGRIDFILTERS'
- Curated allowlist:
  - For ManageRPQosDaily, pre-build a curated ApiName list and join kind=inner to restrict scope.

### Cross-cluster/DB & Sharding
- Cross-cluster sources:
  - ARM analytics: cluster('armprodgbl.eastus') (via Unionizer function wrapper)
  - DevTools telemetry: cluster('ddtelinsights')
- Qualification:
  - Either use registered functions (e.g., Unionizer('Requests','HttpIncomingRequests')) or explicitly reference cluster()/database() if needed.
- Sharded EU/global patterns:
  - Union regional shards, normalize, then summarize:
    - FeatureTrackV2_Daily union FeatureTrackV2_EU_Daily
    - RuntimeRequestsGroups_Daily union RuntimeRequestsGroups_EU_Daily
  - Order: union → normalize keys/time → summarize

### Table classes
- Fact:
  - BillingUsage_Daily, ResourceMetrics, FeatureTrack*, ConnectionMode_Daily, QoS Daily tables, ManageRPQosDaily, ManageResourceTags, Runtime* tables
- Snapshot (latest state or periodic snapshot):
  - RPSettingLatest (config), Cached_*_Snapshot (OKR/ARR/Revenue/Subs/Consumption), Cached_TopSubscriptions_Snapshot, Retention *_Snapshot
- Pre-aggregated:
  - Cached_*_Snapshot families (OKR/ARR/Revenue/Subs/Consumption), Cached_SubsTotal*_* and flow snapshots
- When to use:
  - Facts for detailed ad-hoc slicing and day-grain analyses
  - Snapshots/pre-aggregates for OKR dashboards, top lists, and consistent KPI views
- Caution:
  - Don’t infer “active” from BillingUsage_Daily alone—gate with connectivity/ResourceMetrics (MaxConnectionCount > 0)

## Entity & Counting Rules (Core Definitions)

- Entity model
  - resource → subscription → customer
  - Keys:
    - Resource: ResourceId (normalize to lowercase; collapse replicas to primary when counting)
    - Subscription: SubscriptionId
    - Customer: CloudCustomerGuid (from SubscriptionMappings); sometimes P360_ID/TPID from CustomerModel
  - Standard grouping levels:
    - Resource-level: ResourceId, Region, SKU, ServiceMode/Kind
    - Subscription-level: SubscriptionId, BillingType, OfferType/Name, SegmentName
    - Customer-level: CloudCustomerGuid, CustomerType (Internal/External)
- Counting rules
  - Distinct counts use dcount(..., 3 or 4) for stability (K=3/4); use consistently across reports
  - Activity definition:
    - Active resource/subscription: MaxConnectionCount > 0 (from ResourceMetrics or per-day ConnectionMode_Daily)
    - LiveRatio buckets (examples): Swift (ActiveDays < 3), Occasional (ActiveDays < 10), Dedicate (else)
  - Revenue/consumption:
    - Replace price literals with placeholders:
      - <UnitPrice_Free>=0.0, <UnitPrice_Standard>, <UnitPrice_Premium>
    - Revenue = Quantity * <UnitPrice_SKU>
    - Consumption examples normalize: sum(Quantity)*24 (see queries), or straight sum(Quantity)
  - ServiceMode/Kind:
    - From RPSettingLatest (ServiceMode, Kind; for SocketIO: extract_json('$.socketIO.serviceMode', Extras))
  - Signal classification:
    - Serverless vs Server mode behavior via ConnectionMode_Daily (ServerlessConnection vs ProxyConnection)

## Canonical Tables
Product: SignalR and Web PubSub
Cluster/Database: cluster("signalrinsights.eastus2").database("SignalRBI")
Query themes this workspace supports: OKR/ARR growth; usage and revenue; customer/subscription/resource flows; SignalR vs Web PubSub vs SocketIO segmentation; QoS and RP QoS; feature tracking; top customers.
Time zone and daily refresh delay: unknown. Be cautious with current-day data (prefer closed periods like last full day/week/month).

Below are the canonical tables, ordered by priority (High → Normal → Low). For each table: what it represents, how/when to use it, similar tables, common filters, full schema, and column explanations inferred from the provided queries.

Notes on conventions seen across queries:
- Always exclude internal/team subscriptions: SubscriptionId !in (SignalRTeamInternalSubscriptionIds).
- Distinguish SignalR vs WebPubSub via ResourceId has 'microsoft.signalrservice/signalr' or '/webpubsub/'.
- Use SKU in ('Free','Standard','Premium') and often exclude 'MessageCount' SKUs when computing revenue/consumption.
- Parse SubscriptionId from ResourceId: parse ResourceId with '/subscriptions/' SubscriptionId '/resourceGroups/' *.
- Join to SubscriptionMappings for enrichment: CustomerType, SegmentName, BillingType, OfferName/Type.
- Revenue mapping: case(SKU) times Quantity. Replace hardcoded prices with placeholders, e.g., <UnitPrice_Standard>, <UnitPrice_Premium>.
- Activity gating uses MaxConnectionCount_Daily (not listed here) to ensure “active” resources/subscriptions are counted.

------------------------------------------------------------
### Table name: BillingUsage_Daily
- Priority: High
- What this table represents: Daily billable usage facts per resource/SKU/region/subscription. Fact table; no row implies no billable activity that day.
- Freshness expectations: Daily-updated. Current-day may be incomplete; prefer endofmonth/week/day windows for closed periods.
- When to use / When to avoid:
  - Use for revenue, consumption, subscription counts (with dedupe), and segment splits (Internal vs External, BillingType).
  - Use to split by SignalR vs WebPubSub based on ResourceId.
  - Avoid using alone to infer “active” without checking connections (join ResourceMetrics or MaxConnectionCount_*).
  - Avoid using current-day for monthly/weekly commitments; use last closed day/week/month.
- Similar tables & how to choose:
  - ResourceMetrics: telemetry counts (connections/messages); use for activity, not billing.
  - Cached_* snapshots: pre-aggregated outputs for OKR reporting; use for dashboards, not ad-hoc slicing.
- Common Filters:
  - Time: Date >= ago(30d) or bounded to last closed period.
  - Product: ResourceId has 'microsoft.signalrservice/signalr' or contains '/webpubsub/'.
  - Internal exclusion: SubscriptionId !in (SignalRTeamInternalSubscriptionIds).
  - SKU: in ('Free','Standard','Premium') or exclude 'MessageCount' variants.
- Table columns:

| Column        | Type     | Description or meaning |
|---------------|----------|------------------------|
| Date          | datetime | Usage date (day grain). |
| Region        | string   | Azure region where usage occurred. |
| SubscriptionId| string   | Azure subscription GUID. Often parsed from ResourceId. |
| ResourceId    | string   | Full Azure resource ID. Used to distinguish SignalR vs WebPubSub. |
| SKU           | string   | Billing SKU: Free, Standard, Premium, MessageCount variants. |
| Quantity      | real     | Billable quantity for the SKU on that date. |

- Column Explain:
  - Date: primary filter, align to startofday/startofweek/startofmonth for grouping.
  - ResourceId: filter by product type; normalize case; strip replicas for primary resource counts if needed.
  - SKU: compute revenue via Quantity * <UnitPrice_SKU>; exclude MessageCount in “unit revenue” calcs unless explicitly required.
  - Quantity: use sum(Quantity) for total usage and compute paid/consumption slices.

------------------------------------------------------------
### Table name: ResourceMetrics
- Priority: High
- What this table represents: Daily aggregated telemetry metrics per resource (connections, messages, operations). Fact table for activity/volume.
- Freshness expectations: Daily. Current-day partial; prefer using complete days for week/month groupings.
- When to use / When to avoid:
  - Use to measure MaxConnectionCount and message volumes; define active resources (MaxConnectionCount > 0).
  - Use to build activity-based cohorts (HasConnection, LiveRatio via distinct days).
  - Avoid using for billing/revenue; join to BillingUsage_Daily for that.
- Similar tables & how to choose:
  - BillingUsage_Daily for billing counts; combine both for “top customers” or activity revenue blends.
- Common Filters:
  - Date > ago(61d); ResourceId has SignalR/WebPubSub label; parse SubscriptionId for joining; join to RPSettingLatest for ServiceMode/Kind.
- Table columns:

| Column            | Type     | Description or meaning |
|-------------------|----------|------------------------|
| Date              | datetime | Metric date (day grain). |
| Region            | string   | Azure region. |
| ResourceId        | string   | Resource identity (lowercase often used). |
| SumMessageCount   | real     | Total messages per day. |
| MaxConnectionCount| real     | Max concurrent connections per day. |
| AvgConnectionCount| real     | Average connections per day. |
| SumSystemErrors   | real     | System error events summed. |
| SumTotalOperations| real     | Total operations/events processed. |

- Column Explain:
  - MaxConnectionCount: key “activity” gate; > 0 indicates live.
  - SumMessageCount: throughput; used in “top subscriptions” dashboards.
  - Region: ensures regional slicing and AU/EU date alignment windows.

------------------------------------------------------------
### Table name: SubscriptionMappings
- Priority: High
- What this table represents: Dimension for subscription enrichment (CustomerType, SegmentName, BillingType, Offers).
- Freshness expectations: Snapshot-like mapping, updated as data pipelines refresh; exact schedule unknown.
- When to use / When to avoid:
  - Use to enrich BillingUsage_Daily/ResourceMetrics with customer and billing context.
  - Avoid as a driving table for counts; use with fact tables via leftouter join.
- Similar tables & how to choose:
  - None; this is the canonical subscription dimension.
- Common Filters:
  - Join key: SubscriptionId.
- Table columns:

| Column         | Type   | Description or meaning |
|----------------|--------|------------------------|
| P360_ID        | string | Customer profile key (if available). |
| CloudCustomerGuid | string | Cloud customer GUID. |
| SubscriptionId | string | Subscription GUID; join key. |
| CustomerType   | string | Typically 'Internal' or 'External'. |
| CustomerName   | string | Customer display name. |
| SegmentName    | string | Segment taxonomy. |
| OfferType      | string | Commercial offer type. |
| OfferName      | string | Offer name. |
| BillingType    | string | Billing category (e.g., Consumption, Commitment). |
| WorkloadType   | string | Workload classification. |
| S500           | string | Additional segmentation flag (internal taxonomy). |

- Column Explain:
  - CustomerType/BillingType: used to compute UsageType = iif(CustomerType=='Internal', 'Internal', BillingType).
  - SegmentName/Offer*: used for segmentation dashboards.

------------------------------------------------------------
### Table name: RPSettingLatest
- Priority: High
- What this table represents: Latest RP-side configuration snapshot per resource (ServiceMode/Kind, security and networking toggles).
- Freshness expectations: Snapshot; row per resource with LastUpdated; schedule unknown.
- When to use / When to avoid:
  - Use to derive ServiceMode (Serverless/Default/ServerMode), Kind (WebPubSub/SocketIO), network/security flags.
  - Avoid for historical trend; use FeatureTrack/Runtime tags for behavior over time.
- Similar tables & how to choose:
  - ConnectionMode_Daily for realized connection mode signals; RPSettingLatest shows configured state.
- Common Filters:
  - Join key: ResourceId (lowercased).
- Table columns:

| Column                 | Type     | Description or meaning |
|------------------------|----------|------------------------|
| ResourceId             | string   | Resource identity (lowercased for joins). |
| Region                 | string   | Azure region. |
| SKU                    | string   | Configured SKU. |
| Kind                   | string   | Service kind: WebPubSub vs SocketIO. |
| State                  | string   | Provisioning/operational state. |
| ServiceMode            | string   | Default/Serverless/Server (if present). |
| IsUpstreamSet          | bool     | Upstream configured. |
| IsEventHandlerSet      | bool     | Event handler configured. |
| EnableTlsClientCert    | bool     | TLS client cert enabled. |
| IsPrivateEndpointSet   | bool     | Private Endpoint set. |
| EnablePublicNetworkAccess | bool  | Public network access enabled. |
| DisableLocalAuth       | bool     | Local auth disabled. |
| DisableAadAuth         | bool     | AAD auth disabled. |
| IsServerlessTimeoutSet | bool     | Serverless timeout configured. |
| AllowAnonymousConnect  | bool     | Anonymous access allowed. |
| EnableRegionEndpoint   | bool     | Regional endpoint enabled. |
| ResourceStopped        | bool     | Resource stopped flag. |
| EnableLiveTrace        | bool     | Live trace enabled. |
| EnableResourceLog      | bool     | Resource log enabled. |
| LastUpdated            | datetime | Last config refresh time. |
| Extras                 | string   | JSON bag with additional settings (e.g., socketIO.serviceMode). |

- Column Explain:
  - ServiceMode/Kind/Extras: used widely to classify resources and SocketIO serverless percentages.
  - Security flags: used for compliance or feature adoption tracking.

------------------------------------------------------------
### Table name: FeatureTrack_Daily
- Priority: High
- What this table represents: Daily feature event counters per resource, used to detect feature usage (e.g., ServerSticky).
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use to detect features presence (sumif(RequestCount, Feature == 'X') > 0).
  - Avoid using alone to attribute SKU without BillingUsage join.
- Similar tables & how to choose:
  - FeatureTrackV2_Daily/EU for categorized/extended properties and EU subset coverage.
- Common Filters:
  - Date windows aligned to last 8–12 weeks; join to BillingUsage_Daily to restrict to active/SKU cohorts.
- Table columns:

| Column        | Type     | Description or meaning |
|---------------|----------|------------------------|
| Date          | datetime | Event date. |
| Feature       | string   | Feature name token. |
| ResourceId    | string   | Resource. |
| SubscriptionId| string   | Subscription GUID. |
| RequestCount  | long     | Requests attributed to the feature on Date. |

- Column Explain:
  - Feature: used as keys in sumif; examples include 'ServerSticky', 'ConnectionCountLimitReached'.

------------------------------------------------------------
### Table name: FeatureTrackV2_Daily
- Priority: High
- What this table represents: V2 feature tracking with Category and Properties (JSON) per day/resource.
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use when you need Category grouping or extra Properties beyond Feature name.
  - Avoid mixing with V1 without normalization.
- Similar tables & how to choose:
  - FeatureTrackV2_EU_Daily: same schema, EU-only data.
- Common Filters: similar to FeatureTrack_Daily.
- Table columns:

| Column        | Type     | Description or meaning |
|---------------|----------|------------------------|
| Date          | datetime | Event date. |
| Feature       | string   | Feature token. |
| Category      | string   | Logical category of feature. |
| ResourceId    | string   | Resource. |
| SubscriptionId| string   | Subscription GUID. |
| Properties    | string   | JSON properties for the event. |
| RequestCount  | long     | Count. |

- Column Explain:
  - Category/Properties: used to refine feature grouping (e.g., normalize Ping subcategories).

------------------------------------------------------------
### Table name: FeatureTrackV2_EU_Daily
- Priority: High
- What this table represents: EU subset of FeatureTrackV2_Daily for data residency.
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use to include EU data; union with FeatureTrackV2_Daily for global coverage.
- Similar tables & how to choose:
  - FeatureTrackV2_Daily; union both for complete view.
- Common Filters: same as above.
- Table columns: same as FeatureTrackV2_Daily.

| Column        | Type     | Description or meaning |
|---------------|----------|------------------------|
| Date          | datetime | Event date. |
| Feature       | string   | Feature token. |
| Category      | string   | Category. |
| ResourceId    | string   | Resource. |
| SubscriptionId| string   | Subscription GUID. |
| Properties    | string   | JSON properties. |
| RequestCount  | long     | Count. |

- Column Explain:
  - Use in union queries; keep columns aligned across shards.

------------------------------------------------------------
### Table name: FeatureTrack_AutoScale_Daily
- Priority: High
- What this table represents: Daily counts for autoscale-related feature tracking (resource-level).
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use to compute proportion of premium resources with autoscale signals.
- Similar tables & how to choose:
  - FeatureTrack tables for general feature usage (not autoscale-specific).
- Common Filters:
  - Date >= startofweek(now(), -12); ResourceId has '/signalr/' or '/webpubsub/'; exclude internal subscriptions; combine with BillingUsage_Daily SKU filters.
- Table columns:

| Column        | Type   | Description or meaning |
|---------------|--------|------------------------|
| Date          | datetime | Event date. |
| Region        | string | Region of event/resource. |
| ResourceId    | string | Resource. |
| SubscriptionId| string | Subscription GUID. |
| RequestCount  | long   | Autoscale-related event count. |

- Column Explain:
  - RequestCount: used for resource counts and proportions after joins to SKU=Premium.

------------------------------------------------------------
### Table name: Cached_ZnOKRARR_Snapshot
- Priority: High
- What this table represents: Pre-aggregated ARR snapshot for zone-level (Zn) OKRs.
- Freshness expectations: Snapshot updated periodically; unknown schedule.
- When to use / When to avoid:
  - Use for ARR trendlines without recomputation.
  - Avoid ad-hoc slicing beyond available dimensions (TimeStamp only).
- Similar tables & how to choose:
  - Cached_DtOKRARR_Snapshot for district/overall OKR ARR.
- Common Filters: TimeStamp windows.
- Table columns:

| Column   | Type     | Description |
|----------|----------|-------------|
| TimeStamp| datetime | Snapshot date. |
| SignalR  | real     | ARR metric for SignalR. |
| WebPubSub| real     | ARR metric for WebPubSub. |

- Column Explain:
  - Use with fullouter-join to inject goal lines as in examples.

------------------------------------------------------------
### Table name: Cached_ZnOKREstRevenueWeekly_Snapshot
- Priority: High
- What this table represents: Weekly estimated revenue snapshot (zone-level), exploded by Service.
- Freshness expectations: Weekly.
- When to use / When to avoid:
  - Use for weekly revenue charts by Service and SKU/segment.
- Similar tables & how to choose:
  - Cached_ZnOKREstRevenueMonthly_Snapshot for month grain.
- Common Filters: Week windows (startofweek).
- Table columns:

| Column       | Type     | Description or meaning |
|--------------|----------|------------------------|
| Week         | datetime | Week start. |
| SKU          | string   | Free/Standard/Premium or rollup token. |
| CustomerType | string   | From mapping. |
| SegmentName  | string   | Segment. |
| Service      | string   | 'SignalR' or 'WebPubSub' or combined tokens. |
| Income       | real     | Estimated revenue amount. |

- Column Explain:
  - Income computed upstream with <UnitPrice_SKU> mapping over Quantity in BillingUsage_Daily.

------------------------------------------------------------
### Table name: Cached_ZnOKREstRevenueMonthly_Snapshot
- Priority: High
- What this table represents: Monthly estimated revenue snapshot (zone-level).
- Freshness expectations: Monthly.
- Common Filters: Month = startofmonth(Date).
- Table columns:

| Column       | Type     | Description or meaning |
|--------------|----------|------------------------|
| Month        | datetime | Month start. |
| SKU          | string   | SKU or rollup. |
| CustomerType | string   | From mapping. |
| SegmentName  | string   | Segment. |
| Service      | string   | Service slice. |
| Income       | real     | Estimated revenue. |

- Column Explain:
  - Use for month-on-month OKR revenue deltas.

------------------------------------------------------------
### Table name: Cached_ZnOKRSubs_Snapshot
- Priority: High
- What this table represents: Subscriber counts snapshot (zone-level).
- Freshness expectations: Snapshot.
- Common Filters: TimeStamp windowing.
- Table columns:

| Column   | Type     | Description or meaning |
|----------|----------|------------------------|
| TimeStamp| datetime | Snapshot date. |
| SignalR  | long     | Subscription count for SignalR. |
| WebPubSub| long     | Subscription count for WebPubSub. |

- Column Explain:
  - Used with external goal curves.

------------------------------------------------------------
### Table name: Cached_ZnOKRSubsWeekly_Snapshot
- Priority: High
- What this table represents: Weekly subscriber counts (zone-level), exploded by Service.
- Freshness expectations: Weekly.
- Table columns:

| Column       | Type     | Description or meaning |
|--------------|----------|------------------------|
| Week         | datetime | Week start. |
| SKU          | string   | SKU or rollup token. |
| CustomerType | string   | From mapping. |
| SegmentName  | string   | Segment. |
| Service      | string   | SignalR/WebPubSub/rollups. |
| SubscriptionCnt | int  | Distinct subscriptions (dcount with K=4). |

- Column Explain:
  - subscription dedup sensitivity uses hash partition (K=4 in samples).

------------------------------------------------------------
### Table name: Cached_ZnOKRSubsMonthly_Snapshot
- Priority: High
- What this table represents: Monthly subscriber counts (zone-level).
- Freshness: Monthly.
- Table columns:

| Column       | Type     | Description |
|--------------|----------|-------------|
| Month        | datetime | Month start. |
| SKU          | string   | SKU or rollup. |
| CustomerType | string   | Customer type. |
| SegmentName  | string   | Segment. |
| Service      | string   | Service slice. |
| SubscriptionCnt | int  | Distinct subs. |

------------------------------------------------------------
### Table name: Cached_CuOKRConsumption_Snapshot
- Priority: High
- What this table represents: Consumption OKR snapshot (customer-level aggregate).
- Freshness: Snapshot.
- Table columns:

| Column    | Type     | Description |
|-----------|----------|-------------|
| TimeStamp | datetime | Snapshot date. |
| Consumption | real   | Total consumption. |
| SignalR   | real     | SignalR portion. |
| WebPubSub | real     | WebPubSub portion. |

------------------------------------------------------------
### Table name: Cached_CuOKRConsumptionWeekly_Snapshot
- Priority: High
- What this table represents: Weekly consumption OKR, exploded by Service.
- Freshness: Weekly.
- Table columns:

| Column       | Type     | Description |
|--------------|----------|-------------|
| Week         | datetime | Week start. |
| SKU          | string   | SKU or rollup. |
| CustomerType | string   | Segment source. |
| SegmentName  | string   | Segment. |
| Service      | string   | Service slice. |
| Consumption  | real     | Consumption total. |

------------------------------------------------------------
### Table name: Cached_CuOKRConsumptionMonthly_Snapshot
- Priority: High
- What this table represents: Monthly consumption OKR.
- Freshness: Monthly.
- Table columns:

| Column       | Type     | Description |
|--------------|----------|-------------|
| Month        | datetime | Month start. |
| SKU          | string   | SKU or rollup. |
| CustomerType | string   | Segment source. |
| SegmentName  | string   | Segment. |
| Service      | string   | Service slice. |
| Consumption  | real     | Consumption total. |

------------------------------------------------------------
### Table name: Cached_DtOKRARR_Snapshot
- Priority: High
- What this table represents: Overall/district-level ARR snapshot with total.
- Freshness: Snapshot.
- Table columns:

| Column   | Type     | Description |
|----------|----------|-------------|
| TimeStamp| datetime | Snapshot date. |
| SignalR  | real     | ARR for SignalR. |
| WebPubSub| real     | ARR for WebPubSub. |
| total    | real     | Total ARR. |

------------------------------------------------------------
### Table name: Cached_DtOKREstRevenueWeekly_Snapshot
- Priority: High
- What this table represents: Weekly estimated revenue (overall), exploded by Service and UsageType.
- Freshness: Weekly.
- Table columns:

| Column       | Type     | Description |
|--------------|----------|-------------|
| Week         | datetime | Week start. |
| SKU          | string   | SKU or rollup. |
| UsageType    | string   | Derived: Internal or BillingType. |
| SegmentName  | string   | Segment. |
| Service      | string   | Service slice. |
| Income       | real     | Estimated revenue. |

------------------------------------------------------------
### Table name: Cached_DtOKREstRevenueMonthly_Snapshot
- Priority: High
- What this table represents: Monthly estimated revenue (overall).
- Freshness: Monthly.
- Table columns:

| Column       | Type     | Description |
|--------------|----------|-------------|
| Month        | datetime | Month start. |
| SKU          | string   | SKU or rollup. |
| UsageType    | string   | Internal or BillingType. |
| SegmentName  | string   | Segment. |
| Service      | string   | Service slice. |
| Income       | real     | Estimated revenue. |

------------------------------------------------------------
### Table name: Cached_DtOKRSubsWeekly_Snapshot
- Priority: High
- What this table represents: Weekly subscription counts (overall), exploded by Service and UsageType.
- Freshness: Weekly.
- Table columns:

| Column       | Type     | Description |
|--------------|----------|-------------|
| Week         | datetime | Week start. |
| SKU          | string   | SKU or rollup. |
| UsageType    | string   | Internal or BillingType. |
| Service      | string   | Service slice. |
| SubscriptionCnt | int  | Distinct subscriptions. |
| SegmentName  | string   | Segment. |

------------------------------------------------------------
### Table name: Cached_DtOKRSubsMonthly_Snapshot
- Priority: High
- What this table represents: Monthly subscription counts (overall).
- Freshness: Monthly.
- Table columns:

| Column       | Type     | Description |
|--------------|----------|-------------|
| Month        | datetime | Month start. |
| SKU          | string   | SKU or rollup. |
| UsageType    | string   | Internal or BillingType. |
| SegmentName  | string   | Segment. |
| Service      | string   | Service slice. |
| SubscriptionCnt | int  | Distinct subscriptions. |

------------------------------------------------------------
### Table name: Cached_SubsTotalWeekly_Snapshot
- Priority: High
- What this table represents: Weekly base table used to compute subscription totals (SignalR/WebPubSub), later joined to SubscriptionMappings for segmentation.
- Freshness expectations: Weekly.
- When to use / When to avoid:
  - Use as the foundation for weekly subscription counts; prefer this over recomputing from raw facts for consistency.
- Common Filters: where ServiceType == 'SignalR' or 'WebPubSub'.
- Table columns (inferred from usage; schema function not exposed here):
  - Week (datetime): Week start.
  - ServiceType (string): 'SignalR' or 'WebPubSub'.
  - SubscriptionId (string): Subscription GUID.
  - Region (string), SKU (string): resource context.
  - HasConnection (bool), LiveRatio (string): activity flags.

- Column Explain:
  - Distinct counts are computed on SubscriptionId grouped by Week and segmentation fields.

------------------------------------------------------------
### Table name: Cached_SubsTotalMonthly_Snapshot
- Priority: High
- What this table represents: Monthly base table for subscription totals (SignalR/WebPubSub).
- Freshness: Monthly.
- Table columns (inferred from usage):
  - Month (datetime), ServiceType, SubscriptionId, Region, SKU, HasConnection (bool), LiveRatio (string).

------------------------------------------------------------
### Table name: Cached_TopSubscriptions_Snapshot
- Priority: High
- What this table represents: Top subscription roster with static metrics and active window; used as a seed list for joining daily metrics to produce Category/Value time series.
- Freshness: Snapshot; updated periodically.
- When to use / When to avoid:
  - Use to drive “top customers” views, then join to ResourceMetrics and BillingUsage_Daily by Date.
  - Avoid interpreting Revenue/Message/Connection as daily here—they are rollup attributes of “topness.”
- Common Filters: Service == 'SignalR' or 'WebPubSub' when slicing.
- Table columns:

| Column         | Type     | Description |
|----------------|----------|-------------|
| SubscriptionId | string   | Subscription identity. |
| Revenue        | real     | Top list revenue indicator (not daily). |
| MaxConnection  | long     | Peak connections metric for ranking. |
| MessageCount   | long     | Message metric for ranking. |
| StartDate      | datetime | Inclusion window start. |
| EndDate        | datetime | Inclusion window end. |
| TopRevenue     | real     | Rank score for revenue. |
| TopConnection  | long     | Rank score for connections. |
| TopMessageCount| long     | Rank score for messages. |
| Rate           | real     | Composite rate for ranking. |
| Service        | string   | Service category for the top list. |

- Column Explain:
  - Use this as a seed list; daily metrics come from joins to ResourceMetrics and BillingUsage_Daily.

------------------------------------------------------------
### Table name: CustomerModel
- Priority: High
- What this table represents: Customer modeling data for subscriptions (customer identity, names, rates, offer/billing attributes).
- Freshness: Snapshot; schedule unknown.
- Access note: Backed by cross-cluster entities (customerdomdata); schema not retrievable via current connection.
- When to use:
  - Enrich top-subscription dashboards with CloudCustomerName, TPName, Offer*, BillingType, rate fields.
- Common Filters: join on SubscriptionId.
- Table columns (inferred strictly from query usage):
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
  - TPID (string)

- Column Explain:
  - CustomerType/BillingType/Offer*: segmentation in “top customers” detail.

------------------------------------------------------------
### Table name: ConnectionMode_Daily
- Priority: High
- What this table represents: Daily realized connection counts by connection mode and ServiceMode.
- Freshness: Daily.
- When to use:
  - Determine if a resource operates in Serverless vs Server mode via connection distributions.
- Common Filters: Date windows; ResourceId has '/signalr/' or '/webpubsub/'.
- Table columns:

| Column             | Type     | Description |
|--------------------|----------|-------------|
| Date               | datetime | Day. |
| ResourceId         | string   | Resource. |
| ServerlessConnection | long   | Serverless connections count. |
| ProxyConnection    | long     | Server mode/proxy connections count. |
| ServiceMode        | string   | Derived mode label. |

- Column Explain:
  - Compare ServerlessConnection vs ProxyConnection to classify behavior.

------------------------------------------------------------
### Table name: OKRv2021
- Priority: High
- What this table represents: OKR metric series with flexible Category/Value pairs; pivoted in reports.
- Freshness: Periodic; schedule unknown.
- When to use:
  - Use for historical OKR tracking; apply evaluate pivot(Category, sum(Value)).
- Table columns:

| Column | Type     | Description |
|--------|----------|-------------|
| Date   | datetime | Observation date. |
| Category | string | Metric category key. |
| Value  | real     | Metric value. |

- Column Explain:
  - Pivot Category to produce wide metric tables for visualization.

------------------------------------------------------------
### Table name: OKRv2021_AWPS
- Priority: High
- What this table represents: OKR metric series for Web PubSub.
- Same schema as OKRv2021.

| Column | Type     | Description |
|--------|----------|-------------|
| Date   | datetime | Observation date. |
| Category | string | Metric category key. |
| Value  | real     | Metric value. |

------------------------------------------------------------
### Table name: OKRv2021_SocketIO
- Priority: High
- What this table represents: OKR series for SocketIO flavor of Web PubSub.
- Same schema as OKRv2021.

| Column | Type     | Description |
|--------|----------|-------------|
| Date   | datetime | Observation date. |
| Category | string | Metric category key. |
| Value  | real     | Metric value. |

------------------------------------------------------------
### Table name: RuntimeResourceTags_Daily
- Priority: High
- What this table represents: Daily runtime tags/flags detected for resources (IsAppService, IsStaticApps, IsProxy, etc.).
- Freshness: Daily.
- When to use:
  - Enrich resource/subscription samples with runtime environment and tag-based features.
- Table columns:

| Column        | Type     | Description |
|---------------|----------|-------------|
| Date          | datetime | Day. |
| ResourceId    | string   | Resource. |
| SubscriptionId| string   | Subscription GUID. |
| ServiceType   | string   | SignalR or WebPubSub. |
| IsAppService  | bool     | Detected App Service integration. |
| IsStaticApps  | bool     | Detected Static Apps usage. |
| IsSample      | bool     | Marked as sample (docs/samples). |
| IsProxy       | bool     | Proxy usage. |
| HasFailure    | bool     | Failure detected. |
| HasSuccess    | bool     | Success detected. |
| Extra         | string   | Additional info (JSON/string). |

- Column Explain:
  - Often summarized to booleans by subscription across 28–29 days for “profile” flags.

------------------------------------------------------------
### Table name: Cached_CustomerFlow_Snapshot
- Priority: Normal
- What this table represents: Weekly/Monthly customer flow base (Category = e.g., New/Churn/Retained) by ServiceType and Partition (Week/Month).
- Freshness: Periodic snapshots.
- Common Filters: ServiceType == 'SignalR' or 'WebPubSub'; Partition == 'Week'/'Month'.
- Table columns:

| Column       | Type     | Description |
|--------------|----------|-------------|
| Category     | string   | Flow bucket. |
| Region       | string   | Region. |
| SKU          | string   | SKU. |
| HasConnection| bool     | Activity flag. |
| LiveRatio    | string   | Swift/Occasional/Dedicate. |
| CustomerCnt  | long     | Distinct customers. |
| Date         | datetime | Week or Month date. |
| ServiceType  | string   | Product. |
| Partition    | string   | 'Week' or 'Month'. |

------------------------------------------------------------
### Table name: Cached_ResourceFlow_Snapshot
- Priority: Normal
- What this table represents: Weekly/Monthly resource flow base by ServiceType/Partition.
- Freshness: Periodic snapshots.
- Table columns:

| Column       | Type     | Description |
|--------------|----------|-------------|
| Category     | string   | Flow bucket. |
| Region       | string   | Region. |
| SKU          | string   | SKU. |
| HasConnection| bool     | Activity flag. |
| LiveRatio    | string   | Activity category. |
| ResourceCnt  | long     | Distinct resources. |
| Date         | datetime | Week/Month date. |
| ServiceType  | string   | Product. |
| Partition    | string   | 'Week' or 'Month'. |

------------------------------------------------------------
### Table name: ResourceFlow_Weekly
- Priority: Normal
- What this table represents: Parameterized function emitting weekly resource flow metrics.
- Freshness: Computed on-demand over snapshots.
- When to use: Use with explicit parameters (startDate, endDate, …).
- Schema: Function requires parameters; schema not returned without parameters. Follow existing usage:
  - ResourceFlow_Weekly(startDate=..., endDate=..., <retention months>) | where Week >= …
  - Expect columns including Week and flow metrics per category; consult function definition in ADX if needed.

------------------------------------------------------------
### Table name: ResourceFlow_Monthly
- Priority: Normal
- As above but month grain. Requires parameters; consult function definition for full schema.

------------------------------------------------------------
### Table name: SubscriptionFlow_Weekly
- Priority: Normal
- Parameterized function for weekly subscription flows. Requires parameters; use startDate/endDate; schema resolved at execution.

------------------------------------------------------------
### Table name: SubscriptionFlow_Monthly
- Priority: Normal
- As above but month grain.

------------------------------------------------------------
### Table name: CustomerFlow_Weekly
- Priority: Normal
- Parameterized function for weekly customer flows. Requires parameters; schema resolved with parameters at execution.

------------------------------------------------------------
### Table name: CustomerFlow_Monthly
- Priority: Normal
- Parameterized function for monthly customer flows.

------------------------------------------------------------
### Table name: ManageResourceTags
- Priority: Normal
- What this table represents: ARM-write-operation rollups on resource tags (counts by RequestName/Tags) joined to SubscriptionMappings.
- Freshness: Daily.
- When to use: Count/tag operations (Create/Update tag variants) by customer/region; exclude Microsoft.Authorization noise.
- Table columns:

| Column       | Type     | Description |
|--------------|----------|-------------|
| Date         | datetime | Day. |
| SubscriptionId| string  | Subscription GUID. |
| ResourceId   | string   | Resource. |
| RequestName  | string   | Operation name. |
| Tags         | string   | Tags snapshot or method annotations. |
| Count        | long     | Operation count. |

- Column Explain:
  - RequestName/Tags: used to build “OperationCount” and resource/subscription distinct counts.

------------------------------------------------------------
### Table name: KPIv2019
- Priority: Normal
- What this table represents: Historical KPI series (2019 schema).
- Freshness: Historical/periodic.
- Columns: not referenced explicitly in provided queries beyond Date filter. Retrieve in ADX if needed before authoring new queries.

------------------------------------------------------------
### Table name: KPI_AWPS
- Priority: Normal
- What this table represents: KPI series for Web PubSub.
- Columns: retrieve in ADX as needed; usage analogous to other KPI/OKR series.

------------------------------------------------------------
### Table name: OKRv2021
- Priority: High
- Already documented above.

------------------------------------------------------------
### Table name: OKRv2021_AWPS
- Priority: High
- Already documented above.

------------------------------------------------------------
### Table name: OKRv2021_SocketIO
- Priority: High
- Already documented above.

------------------------------------------------------------
### Table name: ChurnCustomers_Monthly
- Priority: Normal
- What this table represents: Monthly churn metrics per service type with latest run for each Month.
- Freshness: Monthly; multiple runs per month—use Rank == 1 trick to select the latest.
- Table columns:

| Column        | Type     | Description |
|---------------|----------|-------------|
| Month         | datetime | Month start. |
| ServiceType   | string   | Product. |
| Total         | long     | Total customers. |
| Churn         | long     | Churned customers. |
| Standard      | long     | Standard-tier total. |
| StandardChurn | long     | Standard-tier churn. |
| RunDay        | datetime | Run execution time. |

- Column Explain:
  - Compute rates: StandardChurnRate=1.0*StandardChurn/Standard; OverallChurnRate=1.0*Churn/Total.

------------------------------------------------------------
### Table name: ConvertCustomer_Weekly
- Priority: Normal
- What this table represents: Weekly conversion metrics (Free→Paid/Standard/Premium, Standard→Premium) with latest run per week.
- Freshness: Weekly, multiple runs; use Rank==1 pattern.
- Table columns:

| Column           | Type     | Description |
|------------------|----------|-------------|
| Week             | datetime | Week start. |
| ServiceType      | string   | Product. |
| FreeToStandard   | long     | Conversions. |
| TotalCustomers   | long     | Total customers that week. |
| StandardCustomers| long     | Standard tier customers. |
| RunDay           | datetime | Run time. |
| FreeToPaid       | long     | Alias or computed FreeToPaid. |
| StandardToPremium| long     | Conversions. |
| FreeToPremium    | long     | Conversions. |
| PremiumCustomers | long     | Premium tier customers. |

------------------------------------------------------------
### Table name: SignalRTeamInternalSubscriptionIds
- Priority: Normal
- What this table represents: List of internal/team subscription IDs to exclude.
- Freshness: Snapshot; update as needed.
- Table columns:

| Column         | Type   | Description |
|----------------|--------|-------------|
| SubscriptionId | string | Internal/team subscription GUID. |

------------------------------------------------------------
### Table name: ConnectionMode_Daily
- Priority: High
- Already documented above.

------------------------------------------------------------
### Table name: OperationQoS_Daily
- Priority: Low
- What this table represents: Daily availability/uptime inputs per environment role for control/operation endpoints (SignalR/WebPubSub variants filtered via resourceId contains token).
- Freshness: Daily; derive rolling windows by joining with latest env_time and applying back windows.
- Common Filters: env_time windows; resourceId has 'microsoft.signalrservice/signalr' or contains 'webpubsub'.
- Table columns:

| Column                | Type     | Description |
|-----------------------|----------|-------------|
| env_name              | string   | Environment name. |
| env_time              | datetime | Day. |
| resourceId            | string   | Resource identifier string. |
| env_cloud_role        | string   | Role. |
| env_cloud_roleInstance| string   | Role instance. |
| env_cloud_environment | string   | Cloud environment. |
| env_cloud_location    | string   | Region. |
| env_cloud_deploymentUnit | string| DU. |
| totalUpTimeSec        | long     | Uptime seconds. |
| totalTimeSec          | long     | Total seconds. |

- Column Explain:
  - Qos = sum(UpTime)/sum(TotalTime); SlaAttainment computed across resources.

------------------------------------------------------------
### Table name: ConnectivityQoS_Daily
- Priority: Low
- Same schema as OperationQoS_Daily; used for connectivity SLA calculations (0.995 threshold in samples).

| Column                | Type     | Description |
|-----------------------|----------|-------------|
| env_name              | string   | Environment name. |
| env_time              | datetime | Day. |
| resourceId            | string   | Resource identifier. |
| env_cloud_role        | string   | Role. |
| env_cloud_roleInstance| string   | Role instance. |
| env_cloud_environment | string   | Cloud environment. |
| env_cloud_location    | string   | Region. |
| env_cloud_deploymentUnit | string| DU. |
| totalUpTimeSec        | long     | Uptime seconds. |
| totalTimeSec          | long     | Total seconds. |

------------------------------------------------------------
### Table name: ManageRPQosDaily
- Priority: Low
- What this table represents: Management-plane API QoS rollups (Create/Update/Delete etc.) with results and counts.
- Freshness: Daily.
- Common Filters: CustomerType in ('SignalR','WebPubSub',''); ApiName filtering to exclude 'UNCATEGORY' and irrelevant ops.
- Table columns:

| Column       | Type     | Description |
|--------------|----------|-------------|
| Date         | datetime | Day. |
| ApiName      | string   | RP API name. |
| SubscriptionId| string  | Subscription GUID. |
| CustomerType | string   | Product domain. |
| Region       | string   | Region. |
| Result       | string   | Success/Timeout/CustomerError/etc. |
| Count        | long     | Count. |

- Column Explain:
  - QoS = 1.0*sumif(Count, “good” results)/sum(Count); see queries for exact result sets.

------------------------------------------------------------
### Table name: RuntimeRequestsGroups_Daily
- Priority: Low
- What this table represents: Daily runtime request grouping (Category, Metrics) with counts.
- Freshness: Daily.
- Table columns:

| Column       | Type     | Description |
|--------------|----------|-------------|
| Date         | datetime | Day. |
| Category     | string   | E.g., RestApiScenario, Transport. |
| Metrics      | string   | Normalized metric key. |
| ResourceCount| long     | Distinct resources (by day) for the group. |
| RequestCount | long     | Total requests. |

------------------------------------------------------------
### Table name: RuntimeRequestsGroups_EU_Daily
- Priority: Low
- Same schema as RuntimeRequestsGroups_Daily; EU slice.

| Column       | Type     | Description |
|--------------|----------|-------------|
| Date         | datetime | Day. |
| Category     | string   | Group category. |
| Metrics      | string   | Metric key. |
| ResourceCount| long     | Distinct resources. |
| RequestCount | long     | Total requests. |

------------------------------------------------------------
### Table name: RuntimeTransport_Daily
- Priority: Low
- What this table represents: Daily transport/Framework request counts.
- Freshness: Daily.
- Table columns:

| Column       | Type     | Description |
|--------------|----------|-------------|
| Date         | datetime | Day. |
| Feature      | string   | Feature token (if present). |
| Transport    | string   | Transport protocol. |
| Framework    | string   | Client framework. |
| ResourceId   | string   | Resource. |
| SubscriptionId| string  | Subscription GUID. |
| RequestCount | long     | Count. |

------------------------------------------------------------
### Table name: RuntimeTransport_EU_Daily
- Priority: Low
- Same schema as RuntimeTransport_Daily for EU slice.

| Column       | Type     | Description |
|--------------|----------|-------------|
| Date         | datetime | Day. |
| Feature      | string   | Feature token. |
| Transport    | string   | Transport. |
| Framework    | string   | Framework. |
| ResourceId   | string   | Resource. |
| SubscriptionId| string  | Subscription GUID. |
| RequestCount | long     | Count. |

------------------------------------------------------------
### Table name: AwpsRuntimeRequestsGroups_Daily
- Priority: Low
- What this table represents: Web PubSub runtime request groupings (AWPS domain).
- Freshness: Daily.
- Table columns:

| Column       | Type     | Description |
|--------------|----------|-------------|
| Date         | datetime | Day. |
| Category     | string   | Group category. |
| Metrics      | string   | Metric key (normalized for v2021-* patterns). |
| ResourceCount| long     | Distinct resources. |
| RequestCount | long     | Total requests. |

------------------------------------------------------------
### Table name: KPIv2019
- Priority: Normal
- See above note; use with Date filters; obtain schema before pivoting.

------------------------------------------------------------
### Table name: KPI_AWPS
- Priority: Normal
- See above note; obtain schema before pivot/presentation.

------------------------------------------------------------
### Table name: DeleteSurvey
- Priority: Normal
- What this table represents: Feedback on delete operations (SignalR).
- Freshness: Event-driven.
- Columns (inferred from usage):
  - TIMESTAMP (datetime), Deployment (string), resourceId (string), reason (string), feedback (string).

------------------------------------------------------------
### Table name: DeleteSurveyWebPubSub
- Priority: Normal
- As above for Web PubSub.
- Columns (inferred): TIMESTAMP, Deployment, resourceId, reason, feedback.

------------------------------------------------------------
### Table name: FeedbackSurvey
- Priority: Normal
- What this table represents: Customer survey feedback (SignalR).
- Columns (inferred): TimeStamp (datetime), CESValue (real/int), CVAValue (real/int), Comments (string).

------------------------------------------------------------
### Table name: FeedbackSurveyWebPubSub
- Priority: Normal
- As above for Web PubSub.
- Columns (inferred): TimeStamp, Type (string), CESValue, CVAValue, Comments.

------------------------------------------------------------
### Cross-source tables/functions

### Table name: Unionizer/Requests and Unionizer/HttpIncomingRequests
- Source: cluster("armprodgbl.eastus").database("<ARM analytics>")
- Priority: Low
- What this represents: ARM control plane request logs used to derive EventGrid filter operations on SignalR resources.
- Freshness: Near-real-time ARM ingestion cadence; unknown delay.
- When to use:
  - Detect add/delete EventGrid operations and affected resources/subscriptions.
- Columns (inferred from usage):
  - TIMESTAMP (datetime), targetResourceProvider (string), httpMethod (string), targetResourceType (string), targetUri (string), SourceNamespace (string), subscriptionId (string).

- Common Filters:
  - TIMESTAMP > ago(30d), targetResourceProvider == 'MICROSOFT.SIGNALRSERVICE', httpMethod in ('PUT','DELETE'), targetResourceType == 'SIGNALR/EVENTGRIDFILTERS'.

### Table name: WebTools_Raw
- Source: cluster("ddtelinsights").database("<DevTools>")
- Priority: Low
- What this represents: Visual Studio/WebTools telemetry events used to estimate developer funnel signals for SignalR.
- Freshness: Telemetry; unknown delay.
- Columns (inferred from usage; schema not accessible here):
  - AdvancedServerTimestampUtc (datetime), EventName (string), Properties (dynamic), Measures (dynamic), ExeVersion (string), MacAddressHash (string), ActiveProjectId (string).

- Common Filters:
  - EventName families 'vs/webtools/servicedependencies/state', 'vs/webtools/azuretools/...', 'vs/managedpublish/...'
  - Properties contains 'Microsoft.SignalRService/SignalR'; various state categorizations via Measures.

------------------------------------------------------------
## Additional common patterns and tips
- Time handling:
  - Use startofweek/startofmonth on Date for period grouping and ensure closed periods (exclude current week/month unless using normalized partial-month tricks).
  - Latest period windows often derived from the last common Date in both AU East and West Europe for cross-region comparability.

- Revenue/consumption:
  - Replace numeric price literals with placeholders:
    - <UnitPrice_Free>=0, <UnitPrice_Standard>, <UnitPrice_Premium> for revenue.
    - Consumption often = Quantity*24 or straight Quantity depending on scenario; keep consistent with upstream definition.

- Active resource gating:
  - Join to ResourceMetrics (MaxConnectionCount) or to MaxConnectionCount_Daily to ensure you count only live/active resources/subscriptions.

- Service discrimination:
  - SignalR vs WebPubSub:
    - ResourceId has 'microsoft.signalrservice/signalr' → SignalR.
    - ResourceId contains '/webpubsub/' → Web PubSub.
    - RPSettingLatest.Kind='SocketIO' to identify WebPubSub for SocketIO.

- Internal exclusion:
  - Use SignalRTeamInternalSubscriptionIds for SubscriptionId exclusion in every “customer-facing” metric.

- Counting distincts:
  - Many queries use dcount(..., 4) for stable approximate counts; keep K=4 consistent across dashboards.

- EU vs Global:
  - FeatureTrackV2_EU_Daily and Runtime* _EU tables are EU-only. Union with global shards for complete coverage.

This playbook section focused on canonical table definitions and how to use them in Kusto. For parameterized functions (Flow/Retention series), ensure you pass required arguments (startDate, endDate, etc.) and consult the function bodies in ADX for exact output schemas before building new analyses.

## Views (Reusable Layers)
- Not applicable. The provided content did not include ADX views/functions beyond the parameterized functions already documented in Canonical Tables.

## Query Building Blocks (Copy-paste snippets)

- Time window template with completeness gate
  ```kusto
  // Parameters
  let LookbackDays = 60d;
  let RegionsForGate = dynamic(['australiaeast','westeurope']);
  // Effective end date ensures last full day across regions
  let EffectiveEndDate =
    toscalar(
      BillingUsage_Daily
      | where Date > ago(10d) and Region in (RegionsForGate)
      | summarize regions = dcount(Region) by Date
      | where regions >= 2
      | top 1 by Date desc
      | project Date
    );
  // Apply time window and end gate
  let StartDate = ago(LookbackDays);
  BillingUsage_Daily
  | where Date between (StartDate .. EffectiveEndDate)
  ```

- Canonical time aliasing
  ```kusto
  // QoS: align env_time to Date
  OperationQoS_Daily
  | project-rename Date = env_time
  // Snapshots: align TimeStamp to Date
  Cached_DtOKRARR_Snapshot
  | project-rename Date = TimeStamp
  // Bin to Week/Month
  | extend Week = startofweek(Date), Month = startofmonth(Date)
  ```

- Join template (enrich with SubscriptionMappings; align keys/case)
  ```kusto
  let Facts =
    BillingUsage_Daily
    | where Date >= ago(30d)
    | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
    | extend ResourceId = tolower(ResourceId)
    | parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *;
  Facts
  | join kind=leftouter (SubscriptionMappings | project SubscriptionId, CustomerType, CloudCustomerGuid, SegmentName, BillingType, OfferType, OfferName)
      on SubscriptionId
  | extend UsageType = iif(CustomerType == 'Internal', CustomerType, BillingType)
  ```

- Activity gate join (ensure “active”)
  ```kusto
  // Gate by connections: require any MaxConnectionCount on the same day
  BillingUsage_Daily
  | where Date >= ago(60d)
  | join kind=inner (ResourceMetrics | project Date, ResourceId, MaxConnectionCount)
    on Date, ResourceId
  | where MaxConnectionCount > 0
  ```

- De-dup / latest snapshot per key
  ```kusto
  // Latest config per ResourceId
  RPSettingLatest
  | summarize arg_max(LastUpdated, *) by ResourceId
  // Or day-grain roll-up per resource
  BillingUsage_Daily
  | summarize SKU = max(SKU), Region = max(Region) by Date, ResourceId
  ```

- Important filters (product, SKU, internal)
  ```kusto
  // Product segmentation
  | extend IsSignalR = ResourceId has 'microsoft.signalrservice/signalr',
           IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub'
  // Exclude MessageCount variants
  | where SKU in ('Free','Standard','Premium')
  // Exclude internal/team subscriptions
  | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
  ```

- AI cohort example (resource-name-based)
  ```kusto
  | where ResourceId has 'gpt' or ResourceId has 'ai' or ResourceId has 'ml' or
         ResourceId has 'cognitive' or ResourceId contains 'openai' or ResourceId contains 'chatgpt'
  ```

- ID parsing/derivation and replica normalization
  ```kusto
  // Extract SubscriptionId from ResourceId
  | parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
  // Normalize replicas to primary
  | extend PrimaryResource =
      iif(ResourceId has '/replicas/', substring(ResourceId, 0, indexof(ResourceId, '/replicas/')), ResourceId)
  ```

- Revenue mapping (parameterized)
  ```kusto
  let UnitPrice_Free = 0.0;
  let UnitPrice_Standard = <UnitPrice_Standard>;
  let UnitPrice_Premium = <UnitPrice_Premium>;
  BillingUsage_Daily
  | extend UnitPrice =
      case(SKU == 'Free', UnitPrice_Free,
           SKU == 'Standard', UnitPrice_Standard,
           SKU == 'Premium', UnitPrice_Premium,
           real(null))
  | extend Revenue = iif(isnull(UnitPrice), real(null), UnitPrice * Quantity)
  ```

- EU/global sharded union
  ```kusto
  (FeatureTrackV2_Daily
   | project Date, Feature, Category, ResourceId, SubscriptionId, RequestCount)
  | union
  (FeatureTrackV2_EU_Daily
   | project Date, Feature, Category, ResourceId, SubscriptionId, RequestCount)
  | extend Date = startofday(Date)
  | summarize RequestCount = sum(RequestCount) by Date, Feature, Category, ResourceId, SubscriptionId
  ```

- Rolling QoS window (latest snapshot as end anchor)
  ```kusto
  let Anchor =
    toscalar(OperationQoS_Daily | top 1 by env_time desc | project env_time);
  OperationQoS_Daily
  | where env_time > Anchor - 7d
  | summarize Qos = iif(sum(totalTimeSec) == 0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec))
    by Date = Anchor, Type = 'Rolling7'
  ```

## Example Queries (with explanations)

1) Weekly estimated revenue by SKU and UsageType (SignalR)
- Description: Computes weekly revenue for SignalR subscriptions, excluding internal/team subscriptions and mapping SKUs to unit prices via parameters. Adapt the time window and include/exclude SKUs as needed; switch IsSignalR/IsWebPubSub filters for product focus.
```kusto
let UnitPrice_Free = 0.0;
let UnitPrice_Standard = <UnitPrice_Standard>;
let UnitPrice_Premium = <UnitPrice_Premium>;
let Current = toscalar(BillingUsage_Daily | top 1 by Date desc | project Date);
BillingUsage_Daily
| where ResourceId has 'microsoft.signalrservice/signalr'
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
| where Date >= datetime_add('week', -9, startofweek(Current)) and Date < startofweek(Current)
| extend UnitPrice =
    case(SKU == 'Free', UnitPrice_Free,
         SKU == 'Standard', UnitPrice_Standard,
         SKU == 'Premium', UnitPrice_Premium,
         real(null))
| extend Revenue = iif(isnull(UnitPrice), real(null), UnitPrice * Quantity),
         SKU = iif(SKU != 'MessageCount', strcat(' ', SKU), SKU)
| join kind=leftouter SubscriptionMappings on SubscriptionId
| summarize Total = sum(Quantity), Revenue = sum(Revenue) by Week = startofweek(Date), CustomerType, BillingType, SKU
| extend UsageType = iif(CustomerType == 'Internal', CustomerType, BillingType)
```

2) Monthly subscription counts by SKU with SignalR/WebPubSub segmentation and activity gate
- Description: Builds per-month subscription counts, segments by SKU and product type; applies an activity gate (subscriptions present in MaxConnectionCount_Daily). Adapt the SKU set, segmentation, or cohort filters.
```kusto
let raw =
  BillingUsage_Daily
  | where Date >= startofmonth(now(), -10) and Date < startofmonth(now())
  | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
  | extend isAsrs = ResourceId has 'microsoft.signalrservice/signalr',
           isAwps = ResourceId has 'microsoft.signalrservice/webpubsub',
           isFree = SKU == 'Free', isStandard = SKU == 'Standard', isPremium = SKU == 'Premium'
  | summarize isAsrs = max(isAsrs), isAwps = max(isAwps),
              isFree = max(isFree), isStandard = max(isStandard), isPremium = max(isPremium)
      by Month = startofday(endofmonth(Date)), SubscriptionId
  | join kind=inner (
      MaxConnectionCount_Daily
      | where Date >= startofmonth(now(), -10) and Date < startofmonth(now())
      | summarize count() by Month = startofday(endofmonth(Date)), SubscriptionId
    ) on Month, SubscriptionId
  | join kind=leftouter SubscriptionMappings on SubscriptionId
  | extend UsageType = iif(CustomerType == 'Internal', CustomerType, BillingType)
  | summarize isAsrs = max(isAsrs), isAwps = max(isAwps),
              isFree = max(isFree), isStandard = max(isStandard), isPremium = max(isPremium)
      by Month, SubscriptionId, UsageType, SegmentName;
raw
| where isStandard or isFree or isPremium
| summarize OrJoin = dcount(SubscriptionId, 4),
            AndJoin = dcountif(SubscriptionId, isAwps and isAsrs, 4),
            Asrs = dcountif(SubscriptionId, isAsrs, 4),
            Awps = dcountif(SubscriptionId, isAwps, 4)
  by Month, SKU = ' JOIN(OR)', SegmentName, UsageType
```

3) Daily resource counts with completeness gate and “HasConnection” for SignalR
- Description: Derives EffectiveEndDate using dual-region completeness, then counts resources per day by SKU/Region with an activity flag from ResourceMetrics. Adapt RegionsForGate, lookback, or product label for Web PubSub.
```kusto
let EffectiveEndDate =
  toscalar(
    BillingUsage_Daily
    | where Date > ago(10d) and Region in ('australiaeast','westeurope')
    | summarize regions = dcount(Region) by Date
    | where regions >= 2
    | top 1 by Date desc
    | project Date
  );
BillingUsage_Daily
| where Date > ago(61d) and Date <= EffectiveEndDate
| where ResourceId has 'microsoft.signalrservice/signalr'
| extend SubscriptionId = tostring(split(ResourceId, '/')[2])
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
| summarize SKU = max(SKU), Region = max(Region) by Date, ResourceId
| join kind=leftouter ResourceMetrics on Date, ResourceId
| extend HasConnection = iif(isempty(ResourceId1), false, MaxConnectionCount > 0)
| summarize Total = dcount(ResourceId) by Date, SKU, Region, HasConnection
```

4) Top subscriptions: daily Category/Value time series for SignalR
- Description: Starts from the cached top subscription list, joins daily ResourceMetrics and BillingUsage_Daily to emit time-series pairs (Category, Value). Adapt date window, the Service filter, or add more categories.
```kusto
let label = 'microsoft.signalrservice/signalr';
Cached_TopSubscriptions_Snapshot
| where Service == 'SignalR'
| project SubscriptionId
| join kind=inner (
    ResourceMetrics
    | where Date > startofday(now(), -29) and ResourceId has label
    | parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
    | summarize MaxConnectionCount = sum(MaxConnectionCount), MessageCount = sum(SumMessageCount)
        by Date, SubscriptionId
  ) on SubscriptionId
| join kind=inner (
    let UnitPrice_Free = 0.0;
    let UnitPrice_Standard = <UnitPrice_Standard>;
    let UnitPrice_Premium = <UnitPrice_Premium>;
    BillingUsage_Daily
    | where Date > startofday(now(), -29) and ResourceId has label
    | extend UnitPrice =
        case(SKU == 'Free', UnitPrice_Free,
             SKU == 'Standard', UnitPrice_Standard,
             SKU == 'Premium', UnitPrice_Premium,
             real(null))
    | extend Revenue = iif(isnull(UnitPrice), real(null), UnitPrice * Quantity)
    | summarize Revenue = sum(Revenue),
                PaidUnits = sumif(Quantity, SKU in ('Standard','Premium')),
                ResourceCount = dcount(ResourceId)
      by Date, SubscriptionId
  ) on SubscriptionId, Date
| extend Temp = pack('PaidUnits', PaidUnits, 'Revenue', Revenue, 'Messages', MessageCount, 'Connections', MaxConnectionCount, 'Resources', ResourceCount)
| mv-expand kind=array Temp
| project Date, SubscriptionId, Category = tostring(Temp[0]), Value = toreal(Temp[1])
```

5) Feature usage normalization (SignalR) with EU/global union
- Description: Unions FeatureTrackV2 global and EU, normalizes Category (collapsing Ping variants), filters to SignalR and non-internal subs, joins to BillingUsage_Daily to attach SKU and constrain to non-MessageCount. Adapt Feature, Category normalization, or product filter.
```kusto
(FeatureTrackV2_Daily | project Date, Feature, Category, ResourceId, SubscriptionId, RequestCount)
| union (FeatureTrackV2_EU_Daily | project Date, Feature, Category, ResourceId, SubscriptionId, RequestCount)
| where Date > startofweek(now()) - 56d
| extend Date = startofday(Date),
         Category = case(Feature in ('BlazorServerSide','Samples'), Feature,
                         Category endswith 'Ping', substring(Category, 8, indexof(Category, 'Ping') - 8),
                         Category)
| where ResourceId has 'microsoft.signalrservice/signalr'
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| join kind=inner (BillingUsage_Daily | where SKU !in ('MessageCount','MessageCountPremium')) on Date, ResourceId
| summarize RequestCount = sum(RequestCount), SKU = max(SKU)
  by Week = startofweek(Date), Feature, ResourceId, SubscriptionId, Category
```

6) Manage RP QoS (SignalR) weekly rollup with curated API list
- Description: Curates acceptable ApiName set, then summarizes QoS and total requests weekly by Region plus an Overall rollup. Adapt the ApiName filter and CustomerType for WebPubSub.
```kusto
let CuratedApi =
  ManageRPQosDaily
  | where Date > ago(43d)
  | where ApiName !in ('INVALID','GetResource','OperationList','OperationResult','UpdateSubscription','Internal-ACIS','UNCATEGORY')
  | where ApiName !contains 'acs' and ApiName !contains 'acis'
  | where CustomerType in ('SignalR','')
  | distinct ApiName;
ManageRPQosDaily
| where Date >= startofweek(now(), -8)
| where CustomerType in ('SignalR','')
| where ApiName in (CuratedApi)
| summarize QoS = 1.0*sumif(Count, Result in ('Success','Timeout','CustomerError'))/sum(Count),
            TotalRequest = sum(Count)
  by WeekStart = startofweek(Date), Region
| union (
  ManageRPQosDaily
  | where Date >= startofweek(now(), -8)
  | where CustomerType in ('SignalR','')
  | where ApiName in (CuratedApi)
  | summarize QoS = 1.0*sumif(Count, Result in ('Success','Timeout','CustomerError'))/sum(Count),
              TotalRequest = sum(Count)
    by WeekStart = startofweek(Date), Region = 'Overall'
)
```

7) Connection mode classification (SignalR)
- Description: Shows daily resource counts by ServiceMode based on ConnectionMode_Daily ServerlessConnection/ProxyConnection. Useful for Serverless vs Server share. Adapt time window or product filter.
```kusto
ConnectionMode_Daily
| where Date > ago(60d) and ResourceId has 'microsoft.signalrservice/signalr'
| summarize ResourceCount = dcount(ResourceId),
            ConnectionCount = sum(ServerlessConnection) + sum(ProxyConnection)
  by Date, ServiceMode
```

8) ARM EventGrid add/delete detections (SignalR)
- Description: Reads ARM control-plane logs via Unionizer to detect add/delete EventGrid operations on SignalR resources, excluding noise subscriptions. Adapt time window, resource provider/type, and exclusion list as needed.
```kusto
Unionizer('Requests', 'HttpIncomingRequests')
| where TIMESTAMP > ago(30d)
| where targetResourceProvider == 'MICROSOFT.SIGNALRSERVICE'
  and httpMethod in ('PUT','DELETE')
  and targetResourceType == 'SIGNALR/EVENTGRIDFILTERS'
| where subscriptionId !in (/* exclude noisy subscriptions */ '9caf2a1e-9c49-49b6-89a2-56bdec7e3f97', '2085065b-00f8-4cba-9675-ba15f4d4ab66', '685ba005-af8d-4b04-8f16-a7bf38b2eb5a', '1c5b82ee-9294-4568-b0c0-b9c523bc0d86')
| extend ResourceId = substring(targetUri, 33, indexof(targetUri, '?') - 33),
         action = iif(httpMethod == 'PUT', 'AddEventGrid', 'DeleteEventGrid'),
         Date = startofday(TIMESTAMP),
         Location = trim_end('RPF', trim_start('csm', SourceNamespace))
| distinct Date, ResourceId, subscriptionId, action, Location
```

9) DevTools (VS) SignalR detection ratio
- Description: Estimates the ratio of publish events where SignalR is detected in project telemetry. Useful for funnel monitoring. Adapt ExeMajorVersion thresholds, events, or add cohort filters.
```kusto
let Publish =
  WebTools_Raw
  | where AdvancedServerTimestampUtc >= ago(30d)
  | where EventName in ('vs/managedpublish/publish-project','vs/webtools/managedpublish/publish-project')
  | extend IsVs22 = ExeVersion startswith '17.',
           IsNetCore = iif(IsVs22, tobool(Properties['vs.webtools.managedpublish.isnetcoreproject']),
                                    tobool(Properties['vs.managedpublish.isnetcoreproject']))
  | where IsNetCore
  | extend ExeMajorVersion = todecimal(strcat(split(ExeVersion, '.')[0], '.', split(ExeVersion, '.')[1]))
  | where ExeMajorVersion >= 16.1
  | extend Date = startofday(AdvancedServerTimestampUtc)
  | summarize PublishProjectDevCount = dcount(MacAddressHash) by Date;
let Detected =
  WebTools_Raw
  | where AdvancedServerTimestampUtc >= ago(30d)
  | where Properties contains 'Microsoft.SignalRService/SignalR' or
          (EventName == 'vs/webtools/servicedependencies/state'
            and Measures contains 'signalr'
            and Properties['vs.webtools.servicedependencies.profiletype'] == 'remote')
  | extend ExeMajorVersion = todecimal(strcat(split(ExeVersion, '.')[0], '.', split(ExeVersion, '.')[1]))
  | where ExeMajorVersion >= 16.1
  | extend Date = startofday(AdvancedServerTimestampUtc)
  | summarize SignalRDetectedDevCount = dcount(MacAddressHash) by Date;
Publish
| join kind=leftouter Detected on Date
| extend SignalRRatio = todecimal(SignalRDetectedDevCount)/PublishProjectDevCount
| project Date, PublishProjectDevCount, SignalRDetectedDevCount, SignalRRatio
```

10) SocketIO serverless percentage by SKU
- Description: For Web PubSub SocketIO resources, computes the share of serverless resources by week and SKU. Requires RPSettingLatest.Extras socketIO.serviceMode; excludes team subscriptions. Adapt time range and include other modes if needed.
```kusto
let raw =
  RPSettingLatest
  | where ResourceId has '/Microsoft.SignalRService/WebPubSub/' and Kind == 'SocketIO'
  | join kind=inner (BillingUsage_Daily | where Date >= startofweek(now(), -12)) on ResourceId
  | extend IsTeamSubs = iff(SubscriptionId in (SignalRTeamInternalSubscriptionIds), true, false),
           ServiceMode = extract_json('$.socketIO.serviceMode', Extras, typeof(string))
  | project Week = startofweek(Date), ResourceId, SKU = SKU1, IsTeamSubs, ServiceMode;
let totals = raw | summarize TotalSocketIOResourceCount = dcount(ResourceId) by Week;
let serverless = raw | where ServiceMode =~ 'Serverless' | summarize ServerlessCount = dcount(ResourceId) by Week, SKU, IsTeamSubs;
serverless
| join kind=inner totals on Week
| extend ServerlessPercentageByAllSkuTotal = 1.0 * ServerlessCount / TotalSocketIOResourceCount
| project Week, SKU, ServerlessCount, ServerlessPercentageByAllSkuTotal, IsTeamSubs
```

## Reasoning Notes (only if uncertain)
- Timezone is not explicit. We adopt UTC and avoid current day by default, adding completeness gates for daily windows.
- MaxConnectionCount_Daily is referenced in multiple queries but not listed as a canonical table; we treat it as an internal fact/function used purely for activity gating, not as a public dimension.
- For SignalR vs Web PubSub detection, both has and contains are used. We adopt ResourceId has 'microsoft.signalrservice/signalr' and ResourceId has 'microsoft.signalrservice/webpubsub' as the primary tests; contains '/webpubsub/' is accepted when label variants may exist.
- Revenue price points appear as literals (1.61, 2.0) in queries. We replace them with <UnitPrice_Standard> and <UnitPrice_Premium> placeholders to avoid hardcoding and allow parameterization.
- LiveRatio thresholds are inferred from examples (e.g., ActiveDays < 3 → 'Swift', < 10 → 'Occasional'); exact taxonomy may vary—adjust if a canonical function exists upstream.
- Completeness gating uses AU East and West Europe; this appears to be a sentinel pair for coverage. If your workload serves other regions, substitute with your region set or increase the slice requirement.
- Retention snapshots (SubscriptionRetentionSnapshot/CustomerRetentionSnapshot/ResourceRetentionSnapshot) are referenced by queries but not listed in tables; treat them as internal snapshot functions available in the workspace.
- Some Cached_* snapshot names have case variations (e.g., SNAPSHOT vs _Snapshot). We assume both refer to the same logical assets per ADX function naming flexibility; verify in your environment.
- EU/global unions rely on schema equality. If schema drifts, project a shared set of columns before union to avoid type conflicts.