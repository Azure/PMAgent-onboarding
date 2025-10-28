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
  - Pattern: for daily roll-ups, compute last fully landed day by requiring multiple sentinel regions present:
    - EndDate computed from BillingUsage_Daily by ensuring both 'australiaeast' and 'westeurope' report on the same day.
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
    // Effective end date using multi-region completeness gate
    let EndDate =
        toscalar(
            BillingUsage_Daily
            | where Date > ago(10d) and Region in ('australiaeast', 'westeurope')
            | summarize Regions = dcount(Region) by Date
            | where Regions >= 2
            | top 1 by Date desc
            | project Date
        );
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

- Join template
  - Description: Standard alignment of usage with connections and customer mapping; normalize keys and timestamps; prefer leftouter for enrichment.
  - Snippet:
    ```kusto
    let U = BillingUsage_Daily
        | where Date between (StartDate .. EndDate)
        | extend ResourceKey = tolower(ResourceId);
    let C = MaxConnectionCount_Daily
        | where Date between (StartDate .. EndDate)
        | project Date, ResourceKey = tolower(Role);
    U
    | join kind=inner C on Date, ResourceKey
    | join kind=leftouter SubscriptionMappings on SubscriptionId
    | project-away ResourceKey
    ```

- De-dup pattern
  - Description: Use approximate dcount for uniques; when latest-run pick needed (snapshots with RunDay), use row_number partitioned by period; when unioning goals via fullouter, fix duplicate time columns.
  - Snippet:
    ```kusto
    // Stable uniques with precision
    summarize SubscriptionCnt = dcount(SubscriptionId, 4) by Date
    ```
    ```kusto
    // Latest record per month/week by RunDay or rank
    SomeMonthlyTable
    | order by Month asc, RunDay desc
    | extend Rank = row_number(1, prev(Month) != Month)
    | where Rank == 1
    ```
    ```kusto
    // Resolve fullouter time columns
    T
    | join kind=fullouter Goals on TimeStamp
    | extend TimeStamp = iif(isempty(TimeStamp), TimeStamp1, TimeStamp)
    | project-away TimeStamp1
    ```

- Important filters
  - Description: Default exclusions and SKU constraints commonly used across revenue/consumption/OKR.
  - Snippet:
    ```kusto
    // Default exclude internal
    | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)

    // Service scoping
    | where ResourceId has 'microsoft.signalrservice/signalr'   // SignalR
    // or
    | where ResourceId has 'microsoft.signalrservice/webpubsub' // Web PubSub

    // SKU filters
    | where SKU in ('Standard', 'Premium')                      // paid
    | where SKU !in ('MessageCount', 'MessageCountPremium')     // exclude message-only price lines
    ```

- Important Definitions
  - Description: Reusable derivations for business logic used repeatedly in tiles.
  - Snippet:
    ```kusto
    // HasConnection and activity class
    let RM = ResourceMetrics
        | summarize HasConnection = max(MaxConnectionCount) > 0, ActiveDays = dcount(Date) by <Period>=startofweek(Date), ResourceId;
    // Weekly LiveRatio
    | extend LiveRatio = case(ActiveDays < 3, 'Swift', 'Occasional')
    ```
    ```kusto
    // Revenue mapping (use placeholders in new work)
    let UnitPriceStandard = <UnitPriceStandard>;
    let UnitPricePremium  = <UnitPricePremium>;
    let Revenue =
        case(SKU == 'Free', 0.0,
             SKU == 'Standard', UnitPriceStandard,
             SKU == 'Premium', UnitPricePremium, 1.0) * Quantity;
    ```
    ```kusto
    // AI cohort
    | where ResourceId has 'gpt' or ResourceId has 'ai' or ResourceId has 'ml'
       or ResourceId has 'cognitive' or ResourceId contains 'openai' or ResourceId contains 'chatgpt'
    ```

- ID parsing/derivation
  - Description: Extract SubscriptionId from ResourceId; derive PrimaryResource by trimming replicas; parse ARM URIs.
  - Snippet:
    ```kusto
    // From ARM ResourceId
    | parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *

    // Remove /replicas segment for primary resource grouping
    | extend PrimaryResource = iif(ResourceId has '/replicas/', substring(ResourceId, 0, indexof(ResourceId, '/replicas/')), ResourceId)
    ```
    ```kusto
    // From ARM targetUri (Unionizer)
    | extend ResourceId = substring(targetUri, 33, indexof(targetUri, '?') - 33)
    ```

- Sharded union
  - Description: Merge regional shards; normalize case/time before summarize; deduplicate category normalization.
  - Snippet:
    ```kusto
    (FeatureTrackV2_Daily | project Date, ResourceId, SubscriptionId, Feature, Category, RequestCount)
    | union (FeatureTrackV2_EU_Daily | project Date, ResourceId, SubscriptionId, Feature, Category, RequestCount)
    | extend Date = startofday(Date), ResourceId = tolower(ResourceId)
    | summarize RequestCount = sum(RequestCount) by Date, ResourceId, SubscriptionId, Feature, Category
    ```

## Example Queries (with explanations)

- OKR income by service (daily, with gating and mapping)
  - Description: Computes daily income (ARR proxy) by SKU and service (SignalR/WebPubSub) over the last 30–60 days, excludes internal subscriptions and message-only SKUs, aligns usage with connection presence, and enriches with customer segmentation. Use when building OKR revenue tiles and breakdown by service and segment. Adapt by changing ago() windows or gating with EndDate and by altering SKU/segment filters.
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

- AI cohort subscriptions (monthly rolling, with goals)
  - Description: Builds an AI cohort (by ResourceId text patterns) over back-to-back 28-day rolling windows and historical months; counts distinct subscriptions overall and by service type; overlays OKR goals via fullouter join. Use for AI-focused OKR tracking; adapt by adjusting DoM window or cohort keywords.
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
  | where ResourceId has 'gpt' or ResourceId has 'ai' or ResourceId has 'ml' or ResourceId has 'cognitive' or ResourceId contains 'openai' or ResourceId contains 'chatgpt'
  | extend IsSignalR = ResourceId has 'microsoft.signalrservice/signalr', IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub', Month = startofday(Current)
  | summarize SubscriptionCnt = dcount(SubscriptionId), SignalR = dcountif(SubscriptionId, IsSignalR, 4), WebPubSub = dcountif(SubscriptionId, IsWebPubSub, 4) by Month;
  let LatestPeriodBeforeLast = BillingUsage_Daily
  | where Date > Current - 2*DoM and Date <= Current - DoM
  | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
  | where ResourceId has 'gpt' or ResourceId has 'ai' or ResourceId has 'ml' or ResourceId has 'cognitive' or ResourceId contains 'openai' or ResourceId contains 'chatgpt'
  | extend IsSignalR = ResourceId has 'microsoft.signalrservice/signalr', IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub', Month = startofday(Current) - 1h
  | summarize SubscriptionCnt = dcount(SubscriptionId), SignalR = dcountif(SubscriptionId, IsSignalR, 4), WebPubSub = dcountif(SubscriptionId, IsWebPubSub, 4) by Month;
  let Historical = BillingUsage_Daily
  | where Date >= endofmonth(now(), -14) and Date < startofmonth(Current)
  | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
  | where ResourceId has 'gpt' or ResourceId has 'ai' or ResourceId has 'ml' or ResourceId has 'cognitive' or ResourceId contains 'openai' or ResourceId contains 'chatgpt'
  | extend IsSignalR = ResourceId has 'microsoft.signalrservice/signalr', IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub', Month = startofday(endofmonth(Date))
  | summarize SubscriptionCnt = dcount(SubscriptionId), SignalR = dcountif(SubscriptionId, IsSignalR, 4), WebPubSub = dcountif(SubscriptionId, IsWebPubSub, 4) by Month;
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

- Resource totals (daily, HasConnection and completeness gate)
  - Description: Counts distinct resources per day with SKU/Region split and a HasConnection flag by joining ResourceMetrics (MaxConnectionCount > 0). Uses a multi-region EndDate gate. Use for daily active resource totals by SKU and activity; adapt region list or SKU filter as needed.
  ```kusto
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

- Billing paid units and revenue (daily, SignalR)
  - Description: Computes total paid units (Standard+Premium) and revenue by date and SKU, excluding internal subscriptions and gating to landed EndDate. Use for daily paid unit trends and revenue; adapt CustomerType filters with SubscriptionMappings as needed.
  ```kusto
  let EndDate = toscalar(BillingUsage_Daily | where Date > ago(10d) and Region in ('australiaeast', 'westeurope') 
  | summarize counter = dcount(Region) by Date | where counter >= 2 | top 1 by Date desc | project Date);
  BillingUsage_Daily
  | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds) and Date >= ago(60d) and ResourceId has '/signalr/' and Date <= EndDate
  | extend Revenue = case(SKU == 'Free', 0.0, SKU == 'Standard', 1.61, SKU == 'Premium', 2.0, 1.0)*Quantity
  | join kind = leftouter SubscriptionMappings on SubscriptionId
  | summarize Total = sum(Quantity), Revenue = sum(Revenue) by Date, SKU, CustomerType
  ```

- Overview (daily counts across resource/subscription/customer with mapping)
  - Description: Unions ResourceMetrics and BillingUsage_Daily to cover any data gaps; excludes internal; joins SubscriptionMappings; produces daily totals of resources, subscriptions, and customers by CustomerType. Use as a base “north star” roll-up; adapt time window and service filter.
  ```kusto
  ResourceMetrics
  | where Date > ago(61d) and ResourceId has 'microsoft.signalrservice/signalr'
  | parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
  | project Date, SubscriptionId, ResourceId
  | union (BillingUsage_Daily | where Date > ago(61d) and ResourceId has 'microsoft.signalrservice/signalr'
  | project Date, SubscriptionId, ResourceId)
  | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
  | join kind = leftouter SubscriptionMappings on SubscriptionId
  | summarize ResourceTotal = dcount(ResourceId, 3), SubscriptionTotal = dcount(SubscriptionId, 3), CustomerTotal = dcount(CloudCustomerGuid, 3) by Date, CustomerType
  ```

- QoS rolling windows (SignalR, operation QoS)
  - Description: Computes rolling-7 and rolling-28 QoS aggregates anchored to the last env_time; uses a dateFilter join to get the latest anchor. Use for SLA attainment overview; adapt thresholds (>=0.999) or resourceId filter for service types.
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

- Feature: Premium autoscale adoption (SignalR)
  - Description: Tracks the share of Premium SignalR resources using AutoScale each week; excludes internal. Use to monitor feature adoption; adapt for Web PubSub or other feature tracks.
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

- Top subscriptions (SignalR trends)
  - Description: For curated top subscriptions, joins to ResourceMetrics and BillingUsage to produce per-day category/value time series (PaidUnits, Revenue, Messages, Connections, Resources). Use for top-customer deep-dive; adapt Service == 'Web PubSub' for AWPS.
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

## Reasoning Notes (only if uncertain)
- Timestamp/timezone:
  - Possible interpretations: UTC, region-local, customer-local, ingestion-time, event-time.
  - Adopt UTC since queries use startofday/week/month without timezone conversions and VS telemetry field is UTC-labeled.
- Completeness gate:
  - Choices: rely on latest Date, subtract 1 day, use region quorum, or use ingestion metrics.
  - Adopt region quorum (australiaeast + westeurope) shown in multiple queries as stable landing signal.
- Revenue price mapping:
  - Choices: hardcode SKU prices from queries, abstract with placeholders, or compute from a rate table.
  - Adopt placeholders in building blocks and keep literal values in provided examples to preserve behavior, per guidance.
- Uniques precision:
  - Choices: exact count distinct (resource-heavy), dcount default, dcount with precision (3/4).
  - Adopt dcount(., 3|4) as used in product to balance stability and cost.
- AI cohort detection:
  - Choices: filter on tags, SKU, specific offers, or ResourceId keyword heuristics.
  - Adopt ResourceId keyword heuristics as explicitly used; document as heuristic and adaptable.

- Sharded union normalization:
  - Choices: union then summarize directly, or normalize casing/time first.
  - Adopt explicit normalization (tolower, startofday) as seen in queries to prevent double counting and drift.

- Activity classification (LiveRatio):
  - Choices: weekly thresholds (Swift/Occasional), monthly thresholds (Swift/Occasional/Dedicate), or different thresholds.
  - Adopt thresholds explicitly shown in weekly/monthly resource total queries.

- Counting period exclusions:
  - Choices: include current week/month, or exclude via anchor Current.
  - Adopt exclusion via anchor Current to avoid partial period bias, matching product behavior.

- Cross-cluster references:
  - Choices: rely on named functions (Unionizer) vs explicit cluster()/database().
  - Adopt named function when available; recommend cluster() qualification when porting.

- [ ] Identified timestamp column, windows, bin() usage, and timezone assumption.
- [ ] Documented freshness & effective end time strategy.
- [ ] Produced entity model with keys and counting rules for facts vs snapshots.
- [ ] Called out sharded/region tables and `union` normalization.
- [ ] Included default exclusion patterns and cohort filters.
- [ ] Provided ID parsing/derivation snippets.
- [ ] Example queries are copy-paste-ready with guidance.
- [ ] No fabricated fields; placeholders used where needed.

## Canonical Tables

Note: Main cluster/database is signalrinsights.eastus2/SignalRBI unless otherwise specified. Freshness and timezone are not explicitly documented; treat current-day data with caution and prefer closed periods (e.g., completed day/week/month) unless you validate lateness.

### Table name: BillingUsage_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Daily fact table of billed usage by resource/subscription/SKU, used to compute revenue, paid units, and usage segmentation. Zero rows for a day typically implies no billable activity recorded.
- Freshness expectations: Daily updates. Exact ingestion delay unknown; avoid using “today” until data stablizes, or gate with latest available day logic used in sample queries.
- When to use / When to avoid:
  - Use for revenue and paid units by SKU; segment by CustomerType/BillingType via join to SubscriptionMappings.
  - Use to filter SignalR vs Web PubSub via ResourceId has ‘/signalr/’ or ‘/webpubsub/’.
  - Use to exclude internal team subscriptions (SubscriptionId !in SignalRTeamInternalSubscriptionIds()).
  - Avoid using for max connections or messages; join ResourceMetrics for operational metrics.
  - Avoid counting resources directly; use distinct ResourceId with aggregation and other tables for activity status.
- Similar tables & how to choose:
  - ResourceMetrics: operational metrics (connections/messages). Join for activity context.
  - Cached_* snapshots: pre-aggregated weekly/monthly; prefer for trend tiles when up-to-date cached data exists.
- Common Filters:
  - Time: Date >= ago(30d)/startofweek()/startofmonth(); close periods to completed day/week/month.
  - Service: ResourceId has 'microsoft.signalrservice/signalr' or 'microsoft.signalrservice/webpubsub'.
  - SKU: include/exclude Free/Standard/Premium; often exclude MessageCount SKUs.
  - Subscriptions: exclude SignalRTeamInternalSubscriptionIds.
  - Joins: SubscriptionMappings on SubscriptionId.
- Table columns:
  
  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | Date          | datetime | Usage event day (UTC). Used for time-window filtering and rollups. |
  | Region        | string   | Azure region of the resource. |
  | SubscriptionId| string   | Azure subscription GUID; join key to SubscriptionMappings. |
  | ResourceId    | string   | Full ARM Resource ID; use has/contains to identify service type. |
  | SKU           | string   | Pricing tier (e.g., Free, Standard, Premium, MessageCount). |
  | Quantity      | real     | Billed unit quantity; used for paid units and revenue calcs. |
- Column Explain:
  - Date: Primary time grain for daily aggregations; convert to startofweek/startofmonth for coarser trends.
  - ResourceId: Identify service family (‘/signalr/’ vs ‘/webpubsub/’); also extract SubscriptionId when needed.
  - SKU: Drive pricing buckets and paid unit filters; exclude MessageCount in many OKR calculations.
  - Quantity: Core measure; often multiplied by unit price proxy to compute revenue.
  - SubscriptionId: Join to SubscriptionMappings to enrich with CustomerType/Segment/BillingType.

### Table name: MaxConnectionCount_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Daily operational summary with max connections per role/resource, and basic descriptors. Used to validate active usage and gate inclusion against BillingUsage_Daily.
- Freshness expectations: Daily. Exact delay unknown.
- When to use / When to avoid:
  - Use to confirm active resources/subscriptions on specific dates.
  - Use as a join presence check (inner join on Date/Role/ResourceId) for usage analyses.
  - Avoid for message counts; use ResourceMetrics.
  - Avoid as a sole source for revenue; pair with BillingUsage_Daily.
- Similar tables & how to choose:
  - ResourceMetrics: broader operational metrics including messages, avg connections.
- Common Filters:
  - Time: Date >= ago(60d).
  - Joins: tolower(ResourceId) as Role; join on Date and Role/Resource mapping.
- Table columns:
  
  | Column          | Type     | Description or meaning |
  |-----------------|----------|------------------------|
  | Date            | datetime | Day of metric (UTC). |
  | Role            | string   | Lower-cased resource identifier/role key used in joins. |
  | SubscriptionId  | string   | Subscription GUID associated to the role. |
  | CustomerType    | string   | Customer type if present (Internal/External). |
  | Region          | string   | Azure region. |
  | MaxConnectionCount | long  | Max connections observed that day for the role. |
- Column Explain:
  - Date + Role: Join keys against usage data to assert activity on that day.
  - MaxConnectionCount: Indicator of live usage; used to filter resources with actual traffic.

### Table name: SubscriptionMappings (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Subscription master/enrichment mapping for segmentation, offer, billing type, and customer attributes.
- Freshness expectations: Snapshot-like mapping; update cadence unknown. Treat as current-state enrichment.
- When to use / When to avoid:
  - Use to map SubscriptionId to CustomerType (Internal/External), SegmentName, BillingType, Offer metadata.
  - Use in “Top customers/subscriptions” and OKR segment splits.
  - Avoid assuming historical point-in-time accuracy unless queries snapshot mapping by period.
- Similar tables & how to choose:
  - CustomerModel: customer-centric model with P360 and name fields; use when you need customer display/name/TPI linkage.
- Common Filters:
  - Joins: always on SubscriptionId.
- Table columns:
  
  | Column           | Type   | Description or meaning |
  |------------------|--------|------------------------|
  | P360_ID          | string | P360 customer id. |
  | CloudCustomerGuid| string | Customer GUID. |
  | SubscriptionId   | string | Subscription GUID (join key). |
  | CustomerType     | string | Internal/External classification. |
  | CustomerName     | string | Customer name (if available). |
  | SegmentName      | string | Market/segment label. |
  | OfferType        | string | Offer family/type. |
  | OfferName        | string | Offer name. |
  | BillingType      | string | Billing classification (e.g., EA, PAYG). |
  | WorkloadType     | string | Workload tag/category. |
  | S500             | string | Auxiliary segment flag/tag (semantics per usage). |
- Column Explain:
  - SubscriptionId: join key used across most queries.
  - CustomerType, SegmentName, BillingType: primary segmentation axes for dashboards.
  - OfferType/OfferName: used for offer-based slicing.

### Table name: Cached_ZnOKRARR_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Cached OKR ARR (revenue) monthly snapshot, often combined with inline datatable goals to visualize goal vs. actuals.
- Freshness expectations: Snapshot aggregated by TimeStamp; monthly cadence implied by usage; delay unknown.
- When to use / When to avoid:
  - Use for Zn-level ARR OKR tracking visuals.
  - Use when comparing with inline target goals over months.
  - Avoid for per-SKU daily details; use BillingUsage_Daily.
- Similar tables & how to choose:
  - Cached_ZnOKREstRevenueWeekly_Snapshot/Monthly_Snapshot: weekly/monthly estimates by service/SKU.
- Common Filters:
  - Join on TimeStamp to inline goal datatables; filter TimeStamp to historical windows.
- Table columns:
  
  | Column    | Type     | Description or meaning |
  |-----------|----------|------------------------|
  | TimeStamp | datetime | Month-end timestamp for ARR snapshot. |
  | SignalR   | real     | SignalR ARR metric. |
  | WebPubSub | real     | Web PubSub ARR metric. |
- Column Explain:
  - TimeStamp: aligns with month and used for goal joins.
  - SignalR/WebPubSub: split components of total ARR.

### Table name: Cached_ZnOKREstRevenueWeekly_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Cached weekly OKR revenue estimates by service/SKU/segments for Zn scope.
- Freshness expectations: Weekly aggregation; delay unknown.
- When to use / When to avoid:
  - Use for weekly OKR revenue slices and quick visuals.
  - Avoid for raw daily computations; use BillingUsage_Daily if fine-grained recalculation is needed.
- Similar tables & how to choose:
  - Cached_ZnOKREstRevenueMonthly_Snapshot for monthly rollups.
- Common Filters:
  - Week windows; SKU and Service fields used in pivots.
- Table columns:
  
  | Column      | Type     | Description or meaning |
  |-------------|----------|------------------------|
  | Week        | datetime | Week start/end stamp per snapshot logic. |
  | SKU         | string   | SKU tier. |
  | CustomerType| string   | Internal/External classification. |
  | SegmentName | string   | Market/segment label. |
  | Service     | string   | Service label (SignalR/WebPubSub/Total). |
  | Income      | real     | Estimated revenue for that cut. |
- Column Explain:
  - Week: primary grain.
  - Service, SKU, SegmentName: pivot axes used widely.

### Table name: Cached_ZnOKREstRevenueMonthly_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Cached monthly OKR revenue estimates; mirrors weekly snapshot at monthly grain.
- Freshness expectations: Monthly; delay unknown.
- When to use / When to avoid:
  - Use for monthly OKR revenue dashboards.
  - Avoid for day-level breakdowns; use BillingUsage_Daily.
- Similar tables & how to choose:
  - Weekly snapshot for weekly views; this for month.
- Common Filters:
  - Month windows; SKU/Service/SegmentName.
- Table columns:
  
  | Column      | Type     | Description or meaning |
  |-------------|----------|------------------------|
  | Month       | datetime | Month stamp. |
  | SKU         | string   | SKU tier. |
  | CustomerType| string   | Internal/External. |
  | SegmentName | string   | Segment label. |
  | Service     | string   | Service label (SignalR/WebPubSub/Total). |
  | Income      | real     | Estimated monthly income. |
- Column Explain:
  - Month: primary time grain.
  - Service/SKU: rollup axes for ARR.

### Table name: Cached_ZnOKRSubs_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Cached monthly subscription counts for OKR tracking, split by service family.
- Freshness expectations: Monthly; delay unknown.
- When to use / When to avoid:
  - Use for OKR subscription counts and trend vs goal.
  - Avoid for weekly details; use weekly counterpart if exists.
- Similar tables & how to choose:
  - Other OKR subscription snapshots (Dt_*).
- Common Filters:
  - Join on TimeStamp to goal datatables; TimeStamp windows.
- Table columns:
  
  | Column    | Type   | Description or meaning |
  |-----------|--------|------------------------|
  | TimeStamp | datetime | Month stamp. |
  | SignalR   | long   | Subscription count for SignalR. |
  | WebPubSub | long   | Subscription count for Web PubSub. |
- Column Explain:
  - TimeStamp: alignment for goals.
  - SignalR/WebPubSub: separate counts.

### Table name: OKRv2021 (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: OKR KPI fact table with Date/Category/Value triple, used with pivot for visuals.
- Freshness expectations: Not specified; historical series.
- When to use / When to avoid:
  - Use for long-term OKR categories requiring pivoting.
  - Avoid when you need per-subscription granularity.
- Similar tables & how to choose:
  - OKRv2021_AWPS, OKRv2021_SocketIO for AWPS/SocketIO specific streams.
- Common Filters:
  - Date >= fixed baselines.
- Table columns:
  
  | Column  | Type     | Description or meaning |
  |---------|----------|------------------------|
  | Date    | datetime | Measurement date. |
  | Category| string   | KPI category name. |
  | Value   | real     | KPI metric value. |
- Column Explain:
  - Category: used for pivot/evaluate visualization.

### Table name: Cached_CuOKRConsumption_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Cached consumption (e.g., compute/usage-hours) for OKR, split by SignalR/WebPubSub.
- Freshness expectations: Periodic; not explicitly stated.
- When to use / When to avoid:
  - Use to compare consumption vs goals over time.
  - Avoid for day-level recalculations; use BillingUsage_Daily with Quantity*24 patterns.
- Similar tables & how to choose:
  - Weekly/Monthly variants for weekly or monthly visuals.
- Common Filters:
  - Join on TimeStamp to goal datatables.
- Table columns:
  
  | Column    | Type     | Description or meaning |
  |-----------|----------|------------------------|
  | TimeStamp | datetime | Snapshot date (usually month-end). |
  | Consumption | real   | Total consumption measure. |
  | SignalR   | real     | SignalR consumption component. |
  | WebPubSub | real     | WebPubSub consumption component. |
- Column Explain:
  - SignalR/WebPubSub: enable share/stack visuals and service-level tracking.

### Table name: Cached_CuOKRConsumptionWeekly_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Weekly cached consumption, split dimensions similar to revenue snapshots.
- Freshness expectations: Weekly.
- When to use / When to avoid:
  - Use for weekly consumption trends segmented by SKU/CustomerType/Segment.
- Similar tables & how to choose:
  - Monthly snapshot for monthly rollups.
- Common Filters:
  - Week, SKU, CustomerType, SegmentName, Service.
- Table columns:
  
  | Column      | Type     | Description or meaning |
  |-------------|----------|------------------------|
  | Week        | datetime | Week stamp. |
  | SKU         | string   | SKU tier. |
  | CustomerType| string   | Internal/External. |
  | SegmentName | string   | Segment. |
  | Service     | string   | Service slice (Total/SignalR/WebPubSub). |
  | Consumption | real     | Aggregated consumption. |
- Column Explain:
  - Same axes as revenue weekly snapshot for consistency.

### Table name: Cached_CuOKRConsumptionMonthly_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Monthly cached consumption snapshot, aligned to OKR visuals.
- Freshness expectations: Monthly.
- When to use / When to avoid:
  - Use for monthly consumption OKR dashboards.
- Similar tables & how to choose:
  - Weekly variant for week-based reporting.
- Common Filters:
  - Month, SKU, CustomerType, SegmentName, Service.
- Table columns:
  
  | Column      | Type     | Description or meaning |
  |-------------|----------|------------------------|
  | Month       | datetime | Month stamp. |
  | SKU         | string   | SKU tier. |
  | CustomerType| string   | Internal/External. |
  | SegmentName | string   | Segment. |
  | Service     | string   | Service slice. |
  | Consumption | real     | Aggregated monthly consumption. |
- Column Explain:
  - Mirrors weekly fields for symmetry across grains.

### Table name: ResourceMetrics (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Daily operational metrics by resource including message counts, max/avg connections, system errors, and operations.
- Freshness expectations: Daily; actual delay unknown.
- When to use / When to avoid:
  - Use to measure activity: SumMessageCount, MaxConnectionCount, AvgConnectionCount.
  - Use to identify has-connection resources and derive LiveRatio with activity days.
  - Avoid revenue/payed units; join with BillingUsage_Daily for monetization context.
- Similar tables & how to choose:
  - ConnectionMode_Daily: breakdown of connection types; use for serverless/server mode splits.
- Common Filters:
  - ResourceId has '.../signalr' or '.../webpubsub'; Date windows; parse SubscriptionId from ResourceId for mapping joins.
- Table columns:
  
  | Column            | Type     | Description or meaning |
  |-------------------|----------|------------------------|
  | Date              | datetime | Metric day (UTC). |
  | Region            | string   | Azure region. |
  | ResourceId        | string   | ARM Resource ID. |
  | SumMessageCount   | real     | Total messages observed. |
  | MaxConnectionCount| real     | Maximum concurrent connections. |
  | AvgConnectionCount| real     | Average connections. |
  | SumSystemErrors   | real     | System error count. |
  | SumTotalOperations| real     | Total ops count. |
- Column Explain:
  - MaxConnectionCount: used to gate “HasConnection”.
  - SumMessageCount: used for top customer trends.
  - ResourceId: parsed to SubscriptionId for joins to mappings.

### Table name: RPSettingLatest (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Latest resource provider configuration snapshot for resources (SignalR/WebPubSub), including kind, SKU, mode and security flags.
- Freshness expectations: Snapshot with periodic refresh; exact cadence unknown.
- When to use / When to avoid:
  - Use to classify Kind (WebPubSub vs SocketIO), ServiceMode (Default/Serverless), and feature flags (PrivateEndpoint, TLS, etc.).
  - Use in feature tracking (e.g., Aspire via Extras).
  - Avoid time-series analyses; it’s “latest,” not a historical daily rollup.
- Similar tables & how to choose:
  - FeatureTrack_* for feature usage telemetry; RPSettingLatest for configuration state.
- Common Filters:
  - ResourceId has '/Microsoft.SignalRService/SignalR/' or '/WebPubSub/'.
- Table columns:
  
  | Column                   | Type     | Description or meaning |
  |--------------------------|----------|------------------------|
  | ResourceId               | string   | ARM resource id. |
  | Region                   | string   | Resource region. |
  | SKU                      | string   | Pricing tier. |
  | Kind                     | string   | Resource kind (e.g. WebPubSub, SocketIO). |
  | State                    | string   | Provisioning/state. |
  | ServiceMode              | string   | Service mode (Serverless/Default). |
  | IsUpstreamSet            | bool     | Upstream configured. |
  | IsEventHandlerSet        | bool     | Event handler configured. |
  | EnableTlsClientCert      | bool     | TLS client cert enabled. |
  | IsPrivateEndpointSet     | bool     | Private endpoint configured. |
  | EnablePublicNetworkAccess| bool     | Public network access enabled. |
  | DisableLocalAuth         | bool     | Local auth disabled. |
  | DisableAadAuth           | bool     | AAD auth disabled. |
  | IsServerlessTimeoutSet   | bool     | Serverless timeout configured. |
  | AllowAnonymousConnect    | bool     | Anonymous connection allowed. |
  | EnableRegionEndpoint     | bool     | Region endpoint enabled. |
  | ResourceStopped          | bool     | Resource stopped flag. |
  | EnableLiveTrace          | bool     | Live Trace enabled. |
  | EnableResourceLog        | bool     | Resource logs enabled. |
  | LastUpdated              | datetime | Last updated timestamp. |
  | Extras                   | string   | JSON extras (e.g., isAspire, socketIO.serviceMode). |
- Column Explain:
  - Kind/ServiceMode: used for product splits (WebPubSub/SocketIO) and serverless classification.
  - Extras: JSON for feature flags like Aspire and SocketIO details.

### Table name: ConnectionMode_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Daily connection counts by mode (serverless vs proxy/server mode).
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use to split usage by ServiceMode (Serverless vs Proxy).
  - Avoid if you need overall messages; use ResourceMetrics.
- Similar tables & how to choose:
  - ResourceMetrics for broader operational metrics.
- Common Filters:
  - ResourceId has '/signalr/'; Date > ago(60d).
- Table columns:
  
  | Column             | Type     | Description or meaning |
  |--------------------|----------|------------------------|
  | Date               | datetime | Day. |
  | ResourceId         | string   | ARM resource id. |
  | ServerlessConnection| long    | Connections in serverless mode. |
  | ProxyConnection    | long     | Connections via proxy/server mode. |
  | ServiceMode        | string   | Derived service mode. |
- Column Explain:
  - ServerlessConnection/ProxyConnection: core metrics for mode split.

### Table name: CustomerModel (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Customer-centric data model linking customer identity (C360/TPID) with subscription and offer metadata.
- Freshness expectations: Snapshot; cadence unknown.
- When to use / When to avoid:
  - Use to enrich top-customer lists and to produce C360 links.
  - Avoid substituting for SubscriptionMappings when you need specific mapping fields not present here.
- Similar tables & how to choose:
  - SubscriptionMappings for subscription-level segmentation; CustomerModel for P360/TP linkages and names.
- Common Filters:
  - Joins: on SubscriptionId or by P360/TP identifiers.
- Table columns:
  
  | Column                     | Type     | Description or meaning |
  |----------------------------|----------|------------------------|
  | C360_ID                    | string   | C360 customer id. |
  | CustomerName               | string   | Customer name. |
  | CloudCustomerGuid          | string   | Customer GUID. |
  | CloudCustomerName          | string   | Customer name display. |
  | TPID                       | int      | Tenant provider id. |
  | TPName                     | string   | Tenant provider name. |
  | CustomerType               | string   | Internal/External. |
  | SubscriptionId             | string   | Subscription GUID. |
  | FriendlySubscriptionName   | string   | Friendly sub name. |
  | WorkloadType               | string   | Workload classification. |
  | BillingType                | string   | Billing type. |
  | OfferType                  | string   | Offer type. |
  | OfferName                  | string   | Offer name. |
  | CurrentSubscriptionStatus  | string   | Status. |
  | SegmentName                | string   | Segment label. |
  | P360_ID                    | string   | Duplicate id field. |
  | P360_CustomerDisplayName   | string   | Display name. |
  | SubscriptionCreatedDate    | datetime | Creation timestamp. |
  | S500                       | string   | Auxiliary tag. |
- Column Explain:
  - P360/TP fields: use for C360 portal linking and partner segmentation.
  - SubscriptionId: tie-back to BillingUsage_Daily/ResourceMetrics for combined profiles.

### Table name: RuntimeResourceTags_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Daily tagging/flags for resources (by service type), including app service/static apps/proxy markers and success/failure flags.
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use to enrich top subscriptions with platform usage flags (App Service, Static Web Apps, Proxy).
  - Use to find samples usage flags (IsSample).
  - Avoid substituting for precise feature telemetry; pair with FeatureTrack tables when needed.
- Similar tables & how to choose:
  - FeatureTrack_* for feature usage telemetry.
- Common Filters:
  - ServiceType (SignalR/WebPubSub), Date windows, SubscriptionId exclusion.
- Table columns:
  
  | Column         | Type     | Description or meaning |
  |----------------|----------|------------------------|
  | Date           | datetime | Day. |
  | ResourceId     | string   | ARM resource id. |
  | SubscriptionId | string   | Subscription GUID. |
  | ServiceType    | string   | Service family. |
  | IsAppService   | bool     | App Service integration flag. |
  | IsStaticApps   | bool     | Static Web Apps integration flag. |
  | IsSample       | bool     | Sample usage indicator. |
  | IsProxy        | bool     | Uses proxy/server mode. |
  | HasFailure     | bool     | Failure flag detected. |
  | HasSuccess     | bool     | Success flag detected. |
  | Extra          | string   | Additional json or tags. |
- Column Explain:
  - IsAppService/IsStaticApps/IsProxy: key classification in top subscription enrichments.

### Table name: FeatureTrack_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Daily feature-request counts by resource/subscription, used for detecting feature usage (e.g., ServerSticky, scale needed).
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use to compute feature signal counts per day or aggregated to week.
  - Avoid using Properties not present in this version; for richer categorization, use FeatureTrackV2_*.
- Similar tables & how to choose:
  - FeatureTrackV2_Daily/EU for richer categories and EU coverage.
- Common Filters:
  - Date windows; ResourceId service family; exclude internal subs.
- Table columns:
  
  | Column       | Type     | Description or meaning |
  |--------------|----------|------------------------|
  | Date         | datetime | Event day. |
  | Feature      | string   | Feature name. |
  | ResourceId   | string   | ARM resource id. |
  | SubscriptionId| string  | Subscription GUID. |
  | RequestCount | long     | Count of feature-related requests. |
- Column Explain:
  - Feature: used to build boolean flags (e.g., NeededScale > 0).
  - RequestCount: magnitude of feature signals.

### Table name: FeatureTrackV2_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Daily feature tracking with Category dimension and Properties payload, for finer analysis.
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use when feature categories (e.g., Ping groups, Subprotocol) matter.
  - Use to union with EU table for global view.
  - Avoid heavy Properties parsing unless necessary; many queries drop Properties to reduce cost.
- Similar tables & how to choose:
  - FeatureTrackV2_EU_Daily for EU partition; FeatureTrack_Daily for simpler schema.
- Common Filters:
  - Date constraints; ResourceId service family; exclude internal subs.
- Table columns:
  
  | Column     | Type     | Description or meaning |
  |------------|----------|------------------------|
  | Date       | datetime | Event day. |
  | Feature    | string   | Feature label. |
  | Category   | string   | Feature category (cleaned/normalized in queries). |
  | ResourceId | string   | Resource id. |
  | SubscriptionId | string| Subscription GUID. |
  | Properties | string   | JSON properties; often dropped. |
  | RequestCount| long    | Request count. |
- Column Explain:
  - Category: widely used after normalization (e.g., trimming 'Ping').
  - RequestCount: aggregated per week for trend tiles.

### Table name: FeatureTrackV2_EU_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: EU partition of FeatureTrackV2; same schema, used to combine global view.
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use with union to FeatureTrackV2_Daily for worldwide feature usage.
- Similar tables & how to choose:
  - FeatureTrackV2_Daily; pick union for global metrics.
- Common Filters:
  - Same as FeatureTrackV2_Daily.
- Table columns:
  
  | Column     | Type     | Description or meaning |
  |------------|----------|------------------------|
  | Date       | datetime | Event day. |
  | Feature    | string   | Feature label. |
  | Category   | string   | Feature category. |
  | ResourceId | string   | Resource id. |
  | SubscriptionId | string| Subscription GUID. |
  | Properties | string   | JSON properties. |
  | RequestCount| long    | Request count. |
- Column Explain:
  - Same as FeatureTrackV2_Daily.

### Table name: FeatureTrack_AutoScale_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Daily feature telemetry focused on autoscale signals; used to compute counts of resources with autoscale usage.
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use to compute resource counts with autoscale vs total premium resources by week.
  - Avoid revenue analysis; this is feature telemetry.
- Similar tables & how to choose:
  - FeatureTrack_Daily/V2 for other feature categories.
- Common Filters:
  - Date range (weekly windows), ResourceId has '/signalr/' or '/webpubsub/', SKU == 'Premium' from BillingUsage_Daily for denominator joins.
- Table columns:
  
  | Column     | Type     | Description or meaning |
  |------------|----------|------------------------|
  | Date       | datetime | Day. |
  | Region     | string   | Region (when present in joins). |
  | ResourceId | string   | Resource id. |
  | SubscriptionId | string| Subscription GUID. |
  | RequestCount| long    | Request count associated to autoscale feature. |
- Column Explain:
  - RequestCount aggregated by week to derive resource counts.

### Table name: OKRv2021_AWPS (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: AWPS-focused OKR KPI series similar to OKRv2021.
- Freshness expectations: Not specified.
- When to use / When to avoid:
  - Use for AWPS/SocketIO OKR pivoting (often unioned with SocketIO series).
- Common Filters:
  - Date >= baseline.
- Table columns:
  
  | Column  | Type     | Description or meaning |
  |---------|----------|------------------------|
  | Date    | datetime | Metric date. |
  | Category| string   | KPI category. |
  | Value   | real     | KPI value. |
- Column Explain:
  - Same semantic as OKRv2021.

### Table name: OKRv2021_SocketIO (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: SocketIO-specific OKR KPI time series.
- Freshness expectations: Not specified.
- When to use / When to avoid:
  - Use for SocketIO-specific OKR timelines and pivots.
- Table columns:
  
  | Column  | Type     | Description or meaning |
  |---------|----------|------------------------|
  | Date    | datetime | Metric date. |
  | Category| string   | KPI category. |
  | Value   | real     | KPI value. |
- Column Explain:
  - Combine with OKRv2021_AWPS in socketIO analysis.

### Table name: Cached_SubsTotalWeekly_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Weekly cached subscription totals with attributes (region, offer, billing, SKU, customer type, connection flags, LiveRatio).
- Freshness expectations: Weekly.
- When to use / When to avoid:
  - Use for weekly subscription totals and segmentation.
  - Avoid if needing resource-level detail; use resource-level joins.
- Similar tables & how to choose:
  - Cached_SubsTotalMonthly_Snapshot for monthly grain.
- Common Filters:
  - ServiceType == 'SignalR' or 'WebPubSub', Week windows; join to SubscriptionMappings for extra fields (often already present here).
- Table columns:
  
  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | Week          | datetime | Week stamp. |
  | ServiceType   | string   | Service family. |
  | SubscriptionId| string   | Subscription GUID. |
  | Region        | string   | Region. |
  | SKU           | string   | SKU. |
  | HasConnection | bool     | Connection presence flag. |
  | LiveRatio     | string   | Engagement band (Swift/Occasional/Dedicate). |
- Column Explain:
  - HasConnection/LiveRatio: used for quality of usage categorization.

### Table name: Cached_SubsTotalMonthly_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Monthly cached subscription totals (same shape as weekly but at monthly grain).
- Freshness expectations: Monthly.
- When to use / When to avoid:
  - Use for monthly subscription counts and segmentation.
- Table columns:
  
  | Column      | Type     | Description or meaning |
  |-------------|----------|------------------------|
  | Month       | datetime | Month stamp. |
  | ServiceType | string   | Service family. |
  | SubscriptionId| string | Subscription GUID. |
  | Region      | string   | Region. |
  | SKU         | string   | SKU. |
  | HasConnection| bool    | Connection presence. |
  | LiveRatio   | string   | Engagement band. |
- Column Explain:
  - Same as weekly; use for monthly views.

### Table name: Cached_Asrs_TopCustomersWoW_v2_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Asrs (SignalR) weekly over week (WoW) top customer snapshot metrics, including current and delta values with ranks.
- Freshness expectations: Weekly; exact snapshot logic unknown.
- When to use / When to avoid:
  - Use to list top customers by category (Revenue, Messages, MaxConnection, etc.) and compute delta ranks.
  - Avoid recomputing raw metrics; use snapshot as-is for performance.
- Similar tables & how to choose:
  - Cached_Awps_TopCustomersWoW_v2_Snapshot for WebPubSub.
- Common Filters:
  - Sort by DeltaValue asc/desc; limit top N; filter by SKU/CustomerType/Category.
- Table columns:
  
  | Column                  | Type     | Description or meaning |
  |-------------------------|----------|------------------------|
  | P360_ID                 | string   | P360 customer id. |
  | P360_CustomerDisplayName| string   | Display name. |
  | SKU                     | string   | SKU bucket. |
  | CustomerType            | string   | Internal/External. |
  | BillingType             | string   | Billing type. |
  | Category                | string   | Metric category (e.g., Revenue, Connections). |
  | CurrentValue            | real     | Current period value. |
  | P360Url                 | string   | Link to C360. |
  | LastDay                 | datetime | Last day covered. |
  | UsageType               | string   | Usage classification. |
  | CurrentValue1           | real     | Auxiliary current value. |
  | PrevValue               | real     | Previous period value. |
  | W3Value                 | real     | 3-week value. |
  | DeltaValue              | real     | Change vs previous. |
  | Rank                    | long     | Rank by category. |
  | W1Rank                  | long     | 1-week rank. |
  | W3Rank                  | long     | 3-week rank. |
- Column Explain:
  - Category + DeltaValue/Rank: core for “Top customers WoW” tiles.

### Table name: Cached_Awps_TopCustomersWoW_v2_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: WebPubSub counterpart of top customers snapshot.
- Freshness expectations: Weekly.
- When to use / When to avoid:
  - Same as ASRS snapshot but for WebPubSub.
- Table columns:
  
  | Column                  | Type     | Description or meaning |
  |-------------------------|----------|------------------------|
  | P360_ID                 | string   | P360 customer id. |
  | P360_CustomerDisplayName| string   | Display name. |
  | SKU                     | string   | SKU bucket. |
  | CustomerType            | string   | Internal/External. |
  | BillingType             | string   | Billing type. |
  | Category                | string   | Metric category. |
  | CurrentValue            | real     | Current period value. |
  | P360Url                 | string   | Link to C360. |
  | LastDay                 | datetime | Last day covered. |
  | UsageType               | string   | Usage classification. |
  | CurrentValue1           | real     | Auxiliary current value. |
  | PrevValue               | real     | Previous period value. |
  | W3Value                 | real     | 3-week value. |
  | DeltaValue              | real     | Change vs previous. |
  | Rank                    | long     | Rank by category. |
  | W1Rank                  | long     | 1-week rank. |
  | W3Rank                  | long     | 3-week rank. |
- Column Explain:
  - Same usage as ASRS snapshot.

### Table name: Cached_TopSubscriptions_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Subscription-level snapshot of top metrics (revenue, connections, messages), with service, coverage dates, and rates.
- Freshness expectations: Rolling recent window; exact schedule unknown.
- When to use / When to avoid:
  - Use as seed set for joining to daily metrics for trend charts.
  - Use for top subscription tables with enrichment from CustomerModel, RuntimeResourceTags_Daily, FeatureTrack_Daily.
  - Avoid substituting for daily trends; join to ResourceMetrics and BillingUsage_Daily for time series.
- Common Filters:
  - Service == 'SignalR'/'WebPubSub'; date windows last ~28–29 days.
- Table columns:
  
  | Column         | Type     | Description or meaning |
  |----------------|----------|------------------------|
  | SubscriptionId | string   | Subscription GUID. |
  | Revenue        | real     | Revenue over snapshot window. |
  | MaxConnection  | long     | Max connections. |
  | MessageCount   | long     | Total messages. |
  | StartDate      | datetime | Window start. |
  | EndDate        | datetime | Window end. |
  | TopRevenue     | real     | Rank threshold metrics. |
  | TopConnection  | long     | Rank threshold. |
  | TopMessageCount| long     | Rank threshold. |
  | Rate           | real     | Composite performance rate. |
  | Service        | string   | Service category. |
- Column Explain:
  - SubscriptionId: key for enrichment joins.
  - Revenue/MaxConnection/MessageCount: categories used in TopSubscriptionsTrends.

---

### Table name: ManageResourceTags (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Daily ARM management operation tags per resource/subscription (method/category and counts).
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use to analyze management API usage patterns and method mixes, per subscription/resource.
  - Avoid replacing runtime request telemetry; this is control plane.
- Similar tables & how to choose:
  - ManageRPQosDaily for QoS of management APIs.
- Common Filters:
  - Date > ago(30d); ResourceId !has/contains 'Microsoft.Authorization'; RequestName/Tags to group.
- Table columns:
  
  | Column       | Type     | Description or meaning |
  |--------------|----------|------------------------|
  | Date         | datetime | Day. |
  | SubscriptionId| string  | Subscription GUID. |
  | ResourceId   | string   | ARM resource id. |
  | RequestName  | string   | Operation name (e.g., PUT/DELETE categories). |
  | Tags         | string   | Request tags/method details. |
  | Count        | long     | Operation count. |
- Column Explain:
  - RequestName/Tags: drive method categorization.

### Table name: KPIv2019 (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Historical KPI counts at daily grain for legacy/longitudinal metrics.
- Freshness expectations: Historical; new updates unknown.
- When to use / When to avoid:
  - Use for long-run KPI timelines where present.
- Table columns:
  
  | Column           | Type     | Description or meaning |
  |------------------|----------|------------------------|
  | Date             | datetime | Day. |
  | SubscriptionCount| long     | Count of subscriptions. |
  | ResourceCount    | long     | Count of resources. |
- Column Explain:
  - Often filtered by Date >= historical cutoff.

### Table name: ChurnCustomers_Monthly (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Monthly churn stats by service type with totals and standard-tier details.
- Freshness expectations: Monthly; uses latest run per month.
- When to use / When to avoid:
  - Use for churn rates by month; select latest RunDay per Month.
- Table columns:
  
  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | Month         | datetime | Month. |
  | ServiceType   | string   | 'SignalR' or 'WebPubSub'. |
  | Total         | long     | Total customers. |
  | Churn         | long     | Churned customers. |
  | Standard      | long     | Standard-tier total. |
  | StandardChurn | long     | Standard-tier churn. |
  | RunDay        | datetime | Computation timestamp. |
- Column Explain:
  - Use row_number partition by Month to select latest RunDay.

### Table name: ConvertCustomer_Weekly (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Weekly conversion metrics between tiers for each service.
- Freshness expectations: Weekly; select latest RunDay per Week.
- When to use / When to avoid:
  - Use to measure Free->Paid/Premium and Standard->Premium conversions.
- Table columns:
  
  | Column            | Type     | Description or meaning |
  |-------------------|----------|------------------------|
  | Week              | datetime | Week. |
  | ServiceType       | string   | Service family. |
  | FreeToStandard    | long     | Conversions F->S. |
  | TotalCustomers    | long     | Total customers. |
  | StandardCustomers | long     | Standard customers. |
  | RunDay            | datetime | Computation time. |
  | FreeToPaid        | long     | F->Paid (fallback to FreeToStandard as needed). |
  | StandardToPremium | long     | S->P conversions. |
  | FreeToPremium     | long     | F->P direct. |
  | PremiumCustomers  | long     | Premium customers. |
- Column Explain:
  - Apply iif/nullable guards as per queries.

### Table name: ResourceFlow_Weekly (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Function producing weekly resource flow metrics (requires parameters). Used in AWPS dashboards.
- Freshness expectations: Weekly by function execution; unspecified.
- Access note: Not accessible via get_table_schema (function with required parameters). Use in ADX with the right cluster/database and function bindings.
- When to use / When to avoid:
  - Use for resource flow categorization over time when function inputs are known.
  - Avoid if cached snapshot is sufficient: use Cached_ResourceFlow_Snapshot.
- Similar tables & how to choose:
  - Cached_ResourceFlow_Snapshot: use for prematerialized week/month slices.
- Common Filters:
  - Provide startDate/endDate and service selector in function params.

### Table name: ResourceFlow_Monthly (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Function producing monthly resource flow metrics (parameters required).
- Freshness expectations: Monthly.
- Access note: Not accessible via get_table_schema (function with required parameters). Use with parameters in KQL.
- When to use / When to avoid:
  - Use for monthly flow classification when function inputs are known.
  - Prefer cached snapshot if sufficient.
- Similar tables & how to choose:
  - Cached_ResourceFlow_Snapshot for precomputed values.

### Table name: SubscriptionRetentionSnapshot (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Point-in-time subscription cohorts with start/end dates used to compute retention matrices.
- Freshness expectations: Monthly/weekly windows derived; snapshot cadence unknown.
- When to use / When to avoid:
  - Use for cohort-based retention for subscriptions.
- Table columns:
  
  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | SubscriptionId| string   | Subscription GUID. |
  | StartDate     | datetime | Cohort start. |
  | EndDate       | datetime | Retained until. |
- Column Explain:
  - Used with range joins over grids of target months/weeks.

### Table name: CustomerRetentionSnapshot (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Customer-level retention cohorts.
- Table columns:
  
  | Column  | Type     | Description or meaning |
  |---------|----------|------------------------|
  | C360_ID | string   | Customer id. |
  | StartDate| datetime| Start of engagement. |
  | EndDate | datetime | End of retention window. |
- Column Explain:
  - Same pattern as subscription retention but keyed on customer.

### Table name: ResourceRetentionSnapshot (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Resource-level retention cohorts.
- Table columns:
  
  | Column    | Type     | Description or meaning |
  |-----------|----------|------------------------|
  | ResourceId| string   | Resource id. |
  | StartDate | datetime | Start of retention window. |
  | EndDate   | datetime | End of window. |
- Column Explain:
  - Use to compute resource retention matrices.

### Table name: AwpsRetention_SubscriptionSnapshot (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: AWPS-specific subscription retention cohorts.
- Table columns:
  
  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | SubscriptionId| string   | Subscription GUID. |
  | StartDate     | datetime | Start of AWPS cohort. |
  | EndDate       | datetime | Retained to. |
- Column Explain:
  - Use in AWPS retention tiles.

### Table name: AwpsRetention_CustomerSnapshot (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: AWPS-specific customer retention cohorts.
- Table columns:
  
  | Column  | Type     | Description or meaning |
  |---------|----------|------------------------|
  | C360_ID | string   | Customer id. |
  | StartDate| datetime| Start. |
  | EndDate | datetime | End. |
- Column Explain:
  - AWPS customer retention.

### Table name: AwpsRetention_ResourceSnapshot (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: AWPS-specific resource retention cohorts.
- Table columns:
  
  | Column    | Type     | Description or meaning |
  |-----------|----------|------------------------|
  | ResourceId| string   | Resource id. |
  | StartDate | datetime | Start. |
  | EndDate   | datetime | End. |
- Column Explain:
  - AWPS resource retention.

### Table name: Cached_ResourceFlow_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Cached resource flow counts by category/region/SKU and connection flags; includes ServiceType and Partition (Week/Month).
- Freshness expectations: Weekly/Monthly snapshots.
- When to use / When to avoid:
  - Use for resource category splits without invoking functions.
- Table columns:
  
  | Column       | Type     | Description or meaning |
  |--------------|----------|------------------------|
  | Category     | string   | Flow category. |
  | Region       | string   | Region. |
  | SKU          | string   | SKU. |
  | HasConnection| bool     | Connection presence. |
  | LiveRatio    | string   | Engagement band. |
  | ResourceCnt  | long     | Count of resources. |
  | Date         | datetime | Period date. |
  | ServiceType  | string   | Service family. |
  | Partition    | string   | ‘Week’ or ‘Month’. |
- Column Explain:
  - Partition + Date define the time grain.

### Table name: Cached_CustomerFlow_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Cached customer flow counts with segmentation and partitioning.
- Freshness expectations: Weekly/Monthly.
- Table columns:
  
  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | Category      | string   | Category. |
  | Region        | string   | Region. |
  | SKU           | string   | SKU. |
  | HasConnection | bool     | Connection presence. |
  | LiveRatio     | string   | Engagement band. |
  | CustomerType  | string   | Internal/External. |
  | SegmentionType| string   | Segmentation label. |
  | CustomerCnt   | long     | Count of customers. |
  | Date          | datetime | Period date. |
  | ServiceType   | string   | Service family. |
  | Partition     | string   | ‘Week’ or ‘Month’. |
- Column Explain:
  - Used for customer-level breakdowns.

### Table name: KPI_AWPS (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: AWPS KPI counts over time, similar to KPIv2019.
- Freshness expectations: Time series; cadence unknown.
- Table columns:
  
  | Column           | Type     | Description or meaning |
  |------------------|----------|------------------------|
  | Date             | datetime | Date. |
  | SubscriptionCount| long     | Count of subscriptions. |
  | ResourceCount    | long     | Count of resources. |
- Column Explain:
  - Same KPI usage but for AWPS.

### Table name: KPI_SocketIO (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: SocketIO KPI counts.
- Table columns:
  
  | Column           | Type     | Description or meaning |
  |------------------|----------|------------------------|
  | Date             | datetime | Date. |
  | SubscriptionCount| long     | Count of subscriptions. |
  | ResourceCount    | long     | Count of resources. |
- Column Explain:
  - SocketIO-specific KPIs.

### Table name: FeedbackSurvey (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Feedback survey responses for SignalR context (CES/CVA).
- Freshness expectations: Event-based; cadence unknown.
- When to use / When to avoid:
  - Use for simple CES/CVA/Comments listings.
- Table columns:
  
  | Column   | Type     | Description or meaning |
  |----------|----------|------------------------|
  | TimeStamp| datetime | Submission time. |
  | CESValue | int      | CES score. |
  | CVAValue | int      | CVA score. |
  | Comments | string   | Free-text comments. |
- Column Explain:
  - Minimal fields for survey tiles.

### Table name: FeedbackSurveyWebPubSub (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: WebPubSub-specific feedback surveys.
- Table columns:
  
  | Column   | Type     | Description or meaning |
  |----------|----------|------------------------|
  | TimeStamp| datetime | Submission time. |
  | Type     | string   | Survey type. |
  | CESValue | int      | CES score. |
  | CVAValue | int      | CVA score. |
  | Comments | string   | Comments. |
- Column Explain:
  - Same as FeedbackSurvey with Type.

### Table name: DeleteSurvey (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: User feedback on resource deletion for SignalR.
- Freshness expectations: Event-based.
- Table columns:
  
  | Column    | Type     | Description or meaning |
  |-----------|----------|------------------------|
  | TIMESTAMP | datetime | Event time. |
  | Deployment| string   | Deployment name. |
  | resourceId| string   | Resource id. |
  | reason    | string   | Reason text. |
  | feedback  | string   | Feedback text. |
  | objectId  | string   | Object id. |
  | sessionId | string   | Session id. |
- Column Explain:
  - Used for operational sentiment.

### Table name: DeleteSurveyWebPubSub (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Deletion survey for WebPubSub.
- Table columns:
  
  | Column    | Type     | Description or meaning |
  |-----------|----------|------------------------|
  | TIMESTAMP | datetime | Event time. |
  | Deployment| string   | Deployment. |
  | resourceId| string   | Resource id. |
  | reason    | string   | Reason. |
  | feedback  | string   | Feedback. |
  | objectId  | string   | Object id. |
  | sessionId | string   | Session id. |
- Column Explain:
  - Same as SignalR variant.

---

### Table name: OperationQoS_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Low
- What this table represents: Daily uptime QoS metrics by environment/resource for operations layer (up/down seconds).
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use to compute Qos = SumUpTime / SumTotalTime and SLA attainment.
  - Avoid mixing with connectivity QoS; use ConnectivityQoS_Daily separately.
- Common Filters:
  - resourceId has ‘/signalr/’ or contains 'webpubsub'; env_time ranges (rolling 7/28).
- Table columns:
  
  | Column                 | Type     | Description or meaning |
  |------------------------|----------|------------------------|
  | env_name               | string   | Environment. |
  | env_time               | datetime | Time bucket. |
  | resourceId             | string   | Resource id. |
  | env_cloud_role         | string   | Cloud role. |
  | env_cloud_roleInstance | string   | Role instance. |
  | env_cloud_environment  | string   | Cloud env. |
  | env_cloud_location     | string   | Region. |
  | env_cloud_deploymentUnit| string  | Deployment unit. |
  | totalUpTimeSec         | long     | Up time seconds. |
  | totalTimeSec           | long     | Total time seconds. |
- Column Explain:
  - Use env_cloud_location and env_cloud_role for region/resource aggregation.

### Table name: ConnectivityQoS_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Low
- What this table represents: Daily connectivity QoS with same schema as OperationQoS but for connectivity dimension.
- Freshness expectations: Daily.
- Table columns:
  
  | Column                 | Type     | Description or meaning |
  |------------------------|----------|------------------------|
  | env_name               | string   | Environment. |
  | env_time               | datetime | Time bucket. |
  | resourceId             | string   | Resource id. |
  | env_cloud_role         | string   | Cloud role. |
  | env_cloud_roleInstance | string   | Role instance. |
  | env_cloud_environment  | string   | Cloud env. |
  | env_cloud_location     | string   | Region. |
  | env_cloud_deploymentUnit| string  | Deployment unit. |
  | totalUpTimeSec         | long     | Up time seconds. |
  | totalTimeSec           | long     | Total time seconds. |
- Column Explain:
  - Same usage as OperationQoS_Daily; thresholds differ (e.g., 0.995 vs 0.999).

### Table name: ManageRPQosDaily (signalrinsights.eastus2/SignalRBI)
- Priority: Low
- What this table represents: Management plane QoS by APIName/Result with counts, for SignalR/WebPubSub.
- Freshness expectations: Daily.
- When to use / When to avoid:
  - Use for QoS daily/weekly/monthly and rolling windows, filter Core APIs as needed.
- Table columns:
  
  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | Date          | datetime | Day. |
  | ApiName       | string   | Operation/API name. |
  | SubscriptionId| string   | Subscription GUID. |
  | CustomerType  | string   | Service grouping or customer type. |
  | Region        | string   | Region. |
  | Result        | string   | Outcome (Success/Timeout/CustomerError/etc.). |
  | Count         | long     | Request count. |
- Column Explain:
  - Derive QoS as sum(success-like)/sum(total) with filters per queries.

### Table name: RuntimeRequestsGroups_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Low
- What this table represents: Aggregated runtime requests by Category/Metrics with counts and resource coverage.
- Freshness expectations: Daily.
- Table columns:
  
  | Column       | Type     | Description or meaning |
  |--------------|----------|------------------------|
  | Date         | datetime | Day. |
  | Category     | string   | Category (e.g., RestApiScenario, Transport). |
  | Metrics      | string   | Scenario/metric label; normalized in queries. |
  | ResourceCount| long     | Distinct resources. |
  | RequestCount | long     | Sum of requests. |
- Column Explain:
  - Category/Metrics used to build runtime breakdown charts.

### Table name: RuntimeRequestsGroups_EU_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Low
- What this table represents: EU-partitioned runtime requests grouping; same schema.
- Freshness expectations: Daily.
- Table columns: same as RuntimeRequestsGroups_Daily.

### Table name: RuntimeTransport_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Low
- What this table represents: Transport-level runtime telemetry by Feature/Transport/Framework with request counts.
- Freshness expectations: Daily.
- Table columns:
  
  | Column      | Type     | Description or meaning |
  |-------------|----------|------------------------|
  | Date        | datetime | Day. |
  | Feature     | string   | Transport feature. |
  | Transport   | string   | Transport (WebSockets/…); used in Metrics concatenation. |
  | Framework   | string   | Client framework. |
  | ResourceId  | string   | Resource id. |
  | SubscriptionId| string | Subscription id. |
  | RequestCount| long     | Request count. |
- Column Explain:
  - Often unioned with EU variant and normalized into Category='Transport'.

### Table name: RuntimeTransport_EU_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Low
- What this table represents: EU partition of transport telemetry; same schema.
- Freshness expectations: Daily.

### Table name: AwpsRuntimeRequestsGroups_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Low
- What this table represents: AWPS runtime requests grouping; similar schema to runtime requests groups, with AWPS-specific metrics normalization.
- Freshness expectations: Daily.
- Table columns:
  
  | Column       | Type     | Description or meaning |
  |--------------|----------|------------------------|
  | Date         | datetime | Day. |
  | Category     | string   | Category. |
  | Metrics      | string   | Normalized metric string (e.g., v2021-*). |
  | ResourceCount| long     | Distinct resources. |
  | RequestCount | long     | Requests. |
- Column Explain:
  - Queries fix up Metrics content for consistency.

### Table name: Unionizer('Requests','HttpIncomingRequests') (armprodgbl.eastus, database unknown)
- Priority: Low
- What this table represents: Cross-cluster function unionizing ARM logs (Requests/HttpIncomingRequests) to find ARM PUT/DELETE operations for SignalR resources.
- Access note: Cross-cluster and function-based; schema not accessible via this product’s get_table_schema. Use in ADX with the right cluster/database and function bindings.
- When to use / When to avoid:
  - Use for VS ARM requests analysis (EventGrid filters ops).
  - Avoid in product ADX unless cross-cluster connectivity is configured.

### Table name: WebTools_Raw (ddtelinsights, database unknown)
- Priority: Low
- What this table represents: Visual Studio WebTools telemetry raw events used to analyze SignalR detection/provisioning/publish flows.
- Access note: Cross-cluster external dataset; not accessible via current product ADX tools.
- When to use / When to avoid:
  - Use for VS integration analyses (developer counts, publish ratios) if you have access to ddtelinsights cluster.

---

## Column and Query Usage Notes (cross-cutting)
- Time filters and freshness:
  - Use completed periods: endofmonth(Date) for monthly, startofweek(Date) for weekly.
  - Derive “current” anchors via top 1 Date queries; avoid including partial current periods.
- Service family detection:
  - ResourceId has 'microsoft.signalrservice/signalr' (SignalR) vs 'microsoft.signalrservice/webpubsub' (WebPubSub).
  - For premium replicas, strip '/replicas/' to find primary resources.
- Subscription filters:
  - Exclude SignalRTeamInternalSubscriptionIds() in most customer-facing analyses.
  - Join SubscriptionMappings for CustomerType, SegmentName, BillingType.
- Revenue and consumption calculations:
  - Revenue = Quantity * <UnitPriceBySku> with typical proxies (e.g., Standard≈1.61, Premium≈2.0) — use placeholders in documentation and avoid hard-coding in persistent logic.
  - Consumption often uses Quantity * 24 when normalizing to hourly units in OKR queries.
- EU/global splits:
  - FeatureTrackV2_Daily union FeatureTrackV2_EU_Daily for global coverage.
  - Runtime requests often union EU tables.
- Cache vs raw:
  - Prefer Cached_* snapshots for dashboard performance and stable historical series.
  - Use raw tables (BillingUsage_Daily, ResourceMetrics, FeatureTrack_*) for recomputation or ad-hoc slicing.