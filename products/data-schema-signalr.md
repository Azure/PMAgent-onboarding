# SignalR and Web PubSub - Product and Data Overview Template

## 1. Product Overview

SignalR and Web PubSub are Azure managed services for building real-time web applications. This schema onboards the product’s data context so PMAgent can interpret product-specific telemetry and business logic. It is based on the SignalR/Web PubSub Analytics environment hosted in Azure Data Explorer and includes conventions for time windows and completeness gates, entity and counting rules, reusable query building blocks, canonical table descriptions, and example queries for OKR revenue, subscriptions, QoS, feature adoption, top customers, and more.

- Product: SignalR and Web PubSub
- Summary: Power BI report blocks referencing Azure Data Explorer (signalrinsights.eastus2/SignalRBI) with Kusto queries covering OKR analysis, ARR/revenue, usage (connections/messages), service type growth (SignalR/Web PubSub/SocketIO), feature tracking (replicas, auto-scale, Blazor server, Aspire), customer segmentation, top customers, retention, conversions, and more.

## 2. Data Platform Overview

- Data Storage: Azure Data Explorer (ADX)
- Product:
  SignalR and Web PubSub
- Product Nick Names:
  [TODO]Data_Engineer: Fill in commonly used short names or abbreviations (e.g., SignalR, ASRS, Web PubSub, AWPS, SocketIO) to help PMAgent accurately recognize the target product from user conversations.
- Kusto Cluster:
  signalrinsights.eastus2
- Kusto Database:
  SignalRBI
- Access Control:
  [TODO] Data Engineer: If this product’s data has high confidentiality concerns, please specify the allowed groups/users here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.

-----

# SignalR and Web PubSub - Kusto Query Playbook

## Overview
- Product: SignalR and Web PubSub
- Summary: Power BI report blocks referencing Azure Data Explorer (signalrinsights.eastus2/SignalRBI) with Kusto queries covering OKR analysis, ARR/revenue, usage (connections/messages), service type growth (SignalR/Web PubSub/SocketIO), feature tracking (replicas, auto-scale, Blazor server, Aspire), customer segmentation, top customers, retention, conversions, and more.
- Main cluster: signalrinsights.eastus2
- Main database: SignalRBI

## Conventions & Assumptions

- Time semantics
  - Timestamp columns observed:
    - Date: the canonical daily timestamp across most fact tables (BillingUsage_Daily, ResourceMetrics, FeatureTrack*, ManageRPQosDaily, Cached_* snapshots as partition keys).
    - env_time: QoS tables (OperationQoS_Daily, ConnectivityQoS_Daily).
    - AdvancedServerTimestampUtc: Visual Studio “WebTools_Raw” telemetry.
    - TIMESTAMP: ARM request union (“Unionizer”).
  - Canonical Time Column: Date
    - Alias pattern:
      - QoS tables: project-rename Date = env_time
      - VS telemetry: extend Date = startofday(AdvancedServerTimestampUtc)
      - ARM union: extend Date = startofday(TIMESTAMP)
  - Typical windows and binning:
    - Daily: ago(60d), ago(61d), > ago(30d)
    - Weekly windows: startofweek(now(), -8..-12); exclude the current week via Date < startofweek(Current)
    - Monthly windows: startofmonth(now(), -12..-16); often exclude the current month via Date < startofmonth(Current)
    - Cohort/rolling: 7d/28d rolling windows; 28-day “DoM” rolling windows for AI cohorts
  - Timezone: not explicitly stated; default to UTC. Avoid using current-day data unless guarded by a completeness gate.

- Freshness & Completeness Gates
  - Pattern: for daily roll-ups, compute the last fully landed day using sentinel signals. A two-region quorum (e.g., 'australiaeast' + 'westeurope') is a safe option but not required. Choose a gate appropriate to the source:
    - Single-source guard: EndDate = latest Date observed in the fact table within a recent lookback (e.g., > ago(10d)).
    - Parameterized region quorum: sentinelRegions + minRegions (≥1) when regional coverage needs validation.
    - Ingestion/latency metrics-based guard, when available.
    - Conservative fallback: EndDate = startofday(now()) - 1d.
  - Current-week/month often excluded by anchoring to the last landed “Current” date then using Date < startofweek(Current) or Date < startofmonth(Current).
  - Recommendation when unknown: use previous fully landed day; for weekly/monthly, use previous full week/month.

- Joins & Alignment
  - Frequent keys:
    - ResourceId (often normalized with tolower(); for replicas, primary resource derived by trimming "/replicas")
    - SubscriptionId (parsed from ResourceId using parse)
    - Date (or derived Week/Month)
  - Typical join kinds:
    - inner for aligning required fact coverage (e.g., usage + max connections)
    - leftouter to enrich with mappings/settings (SubscriptionMappings, RPSettingLatest)
    - fullouter when overlaying OKR goal targets from datatable()
  - Post-join hygiene:
    - Normalize casing: tolower(ResourceId)
    - Resolve duplicate time columns: extend Date = iif(isempty(Date), Date1, Date); then project-away Date1
    - Drop unused: project-away ...; reduce column fanout
    - Use project-rename to standardize timestamp to Date when joining env_time/other time fields.

- Filters & Idioms
  - Exclude internal/test by default: SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
  - Service scoping by ResourceId:
    - SignalR: ResourceId has 'microsoft.signalrservice/signalr' or contains '/signalr/'
    - Web PubSub: ResourceId has 'microsoft.signalrservice/webpubsub' or contains '/webpubsub/'
  - SKU logic commonly used:
    - Exclude 'MessageCount'/'MessageCountPremium' from paid unit/consumption calculations
    - Paid SKUs: 'Standard', 'Premium'
  - Cohorts:
    - AI cohort filter: ResourceId has/contains 'gpt'/'ai'/'ml'/'cognitive'/'openai'/'chatgpt'
  - Case-insensitive matching: prefer has/contains for robust filtering; normalize strings when needed.

- Cross-cluster/DB & Sharding
  - Cross-cluster sources:
    - Unionizer('Requests','HttpIncomingRequests') from armprodgbl.eastus
    - WebTools_Raw from ddtelinsights
  - Qualify with cluster() and database() or functions where available.
  - Regional shards:
    - FeatureTrackV2_Daily union FeatureTrackV2_EU_Daily
    - RuntimeRequestsGroups_Daily union RuntimeRequestsGroups_EU_Daily
    - Normalize keys and time (tolower(ResourceId), startofday(Date)) before summarize.

- Table classes
  - Fact/events (daily):
    - BillingUsage_Daily, ResourceMetrics, OperationQoS_Daily, ConnectivityQoS_Daily, ManageRPQosDaily, FeatureTrack*_Daily, ConnectionMode_Daily, Runtime* tables, RuntimeResourceTags_Daily
  - Snapshots/pre-aggregated:
    - Cached_*_Snapshot (OKR revenue/consumption/subscriptions, totals, flows, top customers) 
    - Retention snapshots: SubscriptionRetentionSnapshot, CustomerRetentionSnapshot, ResourceRetentionSnapshot (and AWPS equivalents)
  - Use facts when you need granular control and latest completeness gating; use snapshots for fast KPI and historical trend tiles.

- Important Mapping
  - SubscriptionMappings: enriches SubscriptionId with CustomerType, SegmentName, BillingType, Offer*, CloudCustomerGuid, and more.
  - RPSettingLatest: enriches ResourceId with ServiceMode/Kind/Extras (e.g., Aspire flag, SocketIO details).
  - Cached_TopSubscriptions_Snapshot: curated cohort of top subscriptions with summary metrics and lifecyle dates (StartDate/EndDate).
  - ConnectionMode_Daily: derives Serverless vs ServerMode via ServerlessConnection/ProxyConnection aggregates.

## Entity & Counting Rules (Core Definitions)

- Entity model
  - Resource (ResourceId) → Subscription (SubscriptionId) → Customer (CloudCustomerGuid)
  - Standard grouping levels:
    - By Date/Week/Month
    - By SKU, Region
    - By CustomerType, BillingType, SegmentName (from SubscriptionMappings)

- Counting rules
  - Unique counts use approximate counting: dcount(entity, 3|4) for performance and stable tiles.
  - HasConnection: Resource has connection activity if max(MaxConnectionCount) > 0 within the window.
  - LiveRatio (activity class):
    - Weekly: ActiveDays < 3 → 'Swift', else 'Occasional'
    - Monthly: ActiveDays < 3 → 'Swift', ActiveDays < 10 → 'Occasional', else 'Dedicate'
  - Revenue/Income:
    - Derived from Quantity and SKU mapping. Use placeholder prices in reusable snippets and document the mapping; do not mix with MessageCount SKUs in paid-unit aggregations.
  - Consumption:
    - Often computed as sum(Quantity) * 24 (ensure your Quantity semantics match).

- Business definitions (from queries)
  - “AI cohort” customer: resources whose ResourceId matches ai/gpt/ml/cognitive/openai/chatgpt patterns.
  - “Top subscriptions”: from Cached_TopSubscriptions_Snapshot; “IsNew” and “IsRetained” based on StartDate/EndDate relative to recent days.
  - SocketIO service mode (Serverless vs others) parsed from RPSettingLatest.Extras.

## Views (Reusable Layers)
- No explicit reusable Kusto functions/views provided in the source block. Common patterns are implemented inline (see Building Blocks).

## Query Building Blocks (Copy-paste snippets, contains snippets and description)

- Time window template
  - Description: Safely set a time window anchored to the last fully landed day; avoid current-day partials. Provide daily/weekly/monthly pivots.
  - Snippet:
    ```kusto
    // Effective end date guard options
    // 1) Simple last-day guard (single-source)
    let EndDate_simple = toscalar(BillingUsage_Daily | where Date > ago(10d) | top 1 by Date desc | project Date);
    // 2) Parameterized region quorum (choose minRegions = 1 for single-region, 2 for dual-region, etc.)
    let sentinelRegions = dynamic(['australiaeast', 'westeurope']);
    let minRegions = 1; // does not necessarily require two regions
    let EndDate_quorum = toscalar(
        BillingUsage_Daily
        | where Date > ago(10d) and Region in (sentinelRegions)
        | summarize Regions = dcount(Region) by Date
        | where Regions >= minRegions
        | top 1 by Date desc
        | project Date
    );
    // Choose effective EndDate (prefer quorum when available)
    let EndDate = iif(isnull(EndDate_quorum), EndDate_simple, EndDate_quorum);
    // Daily window
    let StartDate = EndDate - 60d;
    BillingUsage_Daily
    | where Date > StartDate and Date <= EndDate
    ```
    ```kusto
    // Anchor to last landed Current date for week/month windows
    let Current = toscalar(<FactTable> | top 1 by Date desc | project Date);
    // Weekly (exclude current week)
    <FactTable>
    | where Date >= datetime_add('week', -9, startofweek(Current)) and Date < startofweek(Current)
    // Monthly (exclude current month)
    <FactTable>
    | where Date >= datetime_add('month', -12, startofmonth(Current)) and Date < startofmonth(Current)
    ```

... (rest of file unchanged)