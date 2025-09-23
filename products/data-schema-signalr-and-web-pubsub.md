# SignalR and Web PubSub - Product and Data Overview Template

## 1. Product Overview

SignalR and Web PubSub provide managed real-time messaging services on Azure. This product area covers:
- Azure SignalR Service: real-time messaging for web/mobile apps.
- Azure Web PubSub (including Socket.IO): publish/subscribe messaging and serverless patterns.

This overview and playbook enable PMAgent to interpret product-specific data correctly for reporting, OKRs, customer cohorts, adoption, QoS, and operational analysis.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**:
SignalR and Web PubSub
- **Product Nick Names**: 
**[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations. Examples to consider: ASRS, SignalR, AWPS, WebPubSub, WPS, SocketIO.
- **Kusto Cluster**:
signalrinsights.eastus2
- **Kusto Database**:
SignalRBI
- **Access Control**:
**[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed groups/users here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

# SignalR and Web PubSub - Kusto Query Playbook

## Overview
- PowerBI report with multiple Azure Data Explorer queries related to SignalR and Web PubSub.
- Primary cluster and database:
  - Cluster: signalrinsights.eastus2
  - Database: SignalRBI

## Conventions & Assumptions

- Time semantics
  - Canonical time column: Date (UTC by default).
  - Other observed time columns and how to normalize:
    - env_time (QoS tables) → project-rename Date = env_time
    - AdvancedServerTimestampUtc (WebTools_Raw) → project Date = startofday(AdvancedServerTimestampUtc)
    - TIMESTAMP (ARM Unionizer) → project Date = startofday(TIMESTAMP)
    - TimeStamp (Snapshot tables like Cached_ZnOKRARR_Snapshot) → project-rename Date = TimeStamp
    - Month/Week buckets are derived via startofmonth(Date), startofweek(Date)
    - End-of-month alignment: use startofday(endofmonth(Date)) when aggregating daily to month-end
  - Typical windows and bins:
    - Daily facts: where Date >= ago(30d|60d)
    - Weekly: startofweek(...) with 8–12-week windows
    - Monthly: startofmonth(...) with 8–16-month windows
  - Timezone: not stated; assume UTC. Be cautious with “today” until ingestion completes.

- Freshness & Completeness Gates
  - Do not use current day/week/month for facts unless anchored. Patterns observed:
    - Effective end-day gate (multi-slice): pick the last day where two sentinel regions report data (australiaeast and westeurope).
    - Anchor “Current” day from the latest available row and backfill rolling windows off that anchor.
  - Recommend:
    - Use prior full day for daily facts when unsure.
    - Use startofweek(now()) - 1d or startofmonth(now()) - 1d as effective end time for weekly/monthly if no explicit anchor is available.

- Joins & Alignment
  - Frequent keys:
    - ResourceId (case-insensitive; often normalized with tolower())
    - SubscriptionId (parsed from ResourceId or taken directly)
    - Date for daily facts, Week and Month for aggregated facts
  - Typical joins:
    - inner for gating/coverage alignment (e.g., to ensure activity or completeness)
    - leftouter for enrichment with dimensions (e.g., SubscriptionMappings)
  - Frequent enrichments and parsing:
    - parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
    - Replicas normalization: if ResourceId has '/replicas/', strip the suffix to primary resource id
    - Lowercase standardization: extend ResourceId = tolower(ResourceId)
  - Post-join hygiene:
    - project-away duplicate columns (e.g., TimeStamp1, SubscriptionId1)
    - project-rename time columns to Date to align downstream logic

- Filters & Idioms
  - Internal/test exclusion:
    - SubscriptionId !in (SignalRTeamInternalSubscriptionIds) or !in (SignalRTeamInternalSubscriptionIds())
  - SKU filters:
    - Exclude MessageCount and MessageCountPremium from revenue/consumption metrics
    - Billable SKUs: Standard, Premium; Free often included for cohort/OKR views
  - Service scoping:
    - SignalR: ResourceId has 'microsoft.signalrservice/signalr'
    - Web PubSub: ResourceId has 'microsoft.signalrservice/webpubsub' or contains '/webpubsub/'
    - SocketIO: RPSettingLatest.Kind == 'SocketIO'
  - AI cohort construction (brand/vertical filter):
    - ResourceId has/contains ‘gpt’, ‘ai’, ‘ml’, ‘cognitive’, ‘openai’, ‘chatgpt’
  - Activity gate:
    - Join to MaxConnectionCount_Daily or ResourceMetrics and test MaxConnectionCount > 0 for “HasConnection”
  - Case-insensitive text filters:
    - Prefer tolower(ResourceId) or use has/contains with lower-cased literals consistently

- Cross-cluster/DB & Sharding
  - Primary data lives in signalrinsights.eastus2/SignalRBI.
  - Some sources are remote:
    - ddTel insights: WebTools_Raw (low priority)
    - ARM telemetry via Unionizer('Requests','HttpIncomingRequests') from armprodgbl.eastus (low priority)
  - Qualify explicitly when needed:
    - cluster('ddtelinsights').database('<db>').WebTools_Raw
    - cluster('armprodgbl.eastus').database('<db>').Unionizer(...)
  - Regional shards:
    - EU vs Non-EU: RuntimeRequestsGroups_Daily vs RuntimeRequestsGroups_EU_Daily and RuntimeTransport_Daily vs RuntimeTransport_EU_Daily
    - Normalize schemas and union before summarize

- Table classes
  - Fact (daily/events):
    - BillingUsage_Daily, ResourceMetrics, MaxConnectionCount_Daily, FeatureTrackV2_Daily, FeatureTrackV2_EU_Daily, FeatureTrack_Daily, FeatureTrack_AutoScale_Daily, ConnectionMode_Daily, OperationQoS_Daily, ConnectivityQoS_Daily, ManageRPQosDaily, RuntimeRequestsGroups_Daily, RuntimeRequestsGroups_EU_Daily, RuntimeTransport_Daily, RuntimeTransport_EU_Daily, RuntimeResourceTags_Daily, ManageResourceTags
  - Snapshot/Pre-aggregated:
    - Cached_*_Snapshot (e.g., totals by week/month, OKR goal overlays, TopSubscriptions), Retention snapshots, KPIv2019, KPI_AWPS, KPI_SocketIO
  - When to use:
    - Prefer Fact tables for newest/high-granularity analysis (with completeness gates)
    - Prefer Snapshots for historical weekly/monthly rollups and business-facing OKRs, retention, and top lists

- Do/Don’t and Gotchas
  - Do
    - Anchor to an effective end day/week/month (avoid current incomplete partitions).
    - Exclude internal/test subscriptions using SignalRTeamInternalSubscriptionIds (or function form).
    - Normalize ResourceId (tolower) and fold replicas to primary when counting.
    - Join to ResourceMetrics for activity gates (HasConnection) when reporting active resources.
    - Use leftouter joins for dimension enrichment (SubscriptionMappings) and inner joins for coverage/activity gates.
    - Use approximate distincts dcount(..., 3|4) for performance at scale.
  - Don’t
    - Don’t include MessageCount SKUs in revenue/consumption unless explicitly needed.
    - Don’t mix EU and Non-EU shards without union and normalization.
    - Don’t rely on “today” without a freshness gate.
  - Gotchas
    - Timezone is unspecified; default to UTC.
    - Snapshots (Cached_*) represent pre-aggregated states; use them for KPI/OKR views rather than recomputing from facts.
    - LiveRatio thresholds differ between weekly and monthly.
    - Features data (FeatureTrack*) often requires co-joining BillingUsage_Daily to ensure the resource has usage in-window.

## Entity & Counting Rules (Core Definitions)

- Entity model and keys
  - Resource → Subscription → Customer
  - Keys:
    - Resource: ResourceId (normalized tolower(), replicas folded to primary id where specified)
    - Subscription: SubscriptionId (from column or parsed from ResourceId)
    - Customer: CloudCustomerGuid (via SubscriptionMappings or CustomerModel)
  - Dimensions:
    - CustomerType, BillingType, SegmentName, OfferType/OfferName, Region, SKU
    - ServiceType or Kind (SignalR, WebPubSub, SocketIO)

- Counting rules
  - Use dcount(..., 3|4) and dcountif(..., condition, 3|4) for approximate distinct counts at scale
  - “Active” resource:
    - HasConnection = (MaxConnectionCount > 0) based on ResourceMetrics join
  - Billable vs Free:
    - Billable SKUs are Standard and Premium; Free often included in full population but excluded from revenue
  - Replicas:
    - Distinct resource counting may fold replicas into their primary ResourceId to avoid double counting
  - Monthly/Weekly rollups:
    - Aggregate by Month = startofmonth(Date) or Week = startofweek(Date)
    - For “end-of-month value,” normalize by dayofmonth(endofmonth(Month)) when comparing growth MoM

## Views (Reusable Layers)
No predefined views were provided. The patterns below are offered as reusable let blocks in Query Building Blocks.

## Query Building Blocks (Copy-paste snippets, contains snippets and description)

- Time window template
  - Description: Anchor to an effective end day using multi-region completeness; derive rolling daily/weekly/monthly windows safely.
  - Snippet:
    ```kusto
    // Effective end-day gate using two sentinel regions
    let EndDate =
        toscalar(
            BillingUsage_Daily
            | where Date > ago(10d) and Region in ('australiaeast','westeurope')
            | summarize Regions = dcount(Region) by Date
            | where Regions >= 2
            | top 1 by Date desc
            | project Date
        );
    // Safe windows avoiding current partial periods
    let DailyStart = ago(60d);
    let WeekEnd = startofweek(EndDate);
    let MonthEnd = startofmonth(EndDate);
    ```
- Join template
  - Description: Standard enrichment and activity gating joins.
  - Snippet:
    ```kusto
    // Normalize IDs and enrich with SubscriptionMappings
    let base =
        BillingUsage_Daily
        | where Date between (ago(30d) .. EndDate)
        | extend ResourceId = tolower(ResourceId)
        | parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
        | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
        | join kind=leftouter SubscriptionMappings on SubscriptionId;

    // Gate to active usage via ResourceMetrics on Date+ResourceId
    base
    | join kind=inner (ResourceMetrics | project Date, ResourceId = tolower(ResourceId), MaxConnectionCount) on Date, ResourceId
    | extend HasConnection = MaxConnectionCount > 0
    ```
- De-dup pattern
  - Description: Remove replica suffix and deduplicate resource counts; standardize case.
  - Snippet:
    ```kusto
    // Fold replicas to primary resource id
    extend ResourceId = tolower(ResourceId);
    extend PrimaryResourceId =
        iif(ResourceId has '/replicas/', substring(ResourceId, 0, indexof(ResourceId, '/replicas/')), ResourceId);
    // Count unique primaries (approximate)
    summarize ResourceCnt = dcount(PrimaryResourceId, 3) by Date
    ```
- Important filters
  - Description: Common population and cohort filters.
  - Snippets:
    ```kusto
    // Exclude internal/test subscriptions
    | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
    ```
    ```kusto
    // Service scoping
    | where ResourceId has 'microsoft.signalrservice/signalr'   // SignalR
    // or
    | where ResourceId has 'microsoft.signalrservice/webpubsub' // Web PubSub
    ```
    ```kusto
    // Billable SKU cohort
    | where SKU in ('Standard','Premium')
    // Exclude non-revenue SKUs for revenue/consumption
    | where SKU !in ('MessageCount','MessageCountPremium')
    ```
    ```kusto
    // AI cohort (brand/keyword)
    | where ResourceId has 'gpt' or ResourceId has 'ai' or ResourceId has 'ml'
       or ResourceId has 'cognitive' or ResourceId contains 'openai' or ResourceId contains 'chatgpt'
    ```
- Important Definitions
  - External customers: CustomerType == 'External' (via SubscriptionMappings)
  - Billable customers: Subscriptions with SKU in ('Standard', 'Premium')
  - Active resource: HasConnection = (MaxConnectionCount > 0)
  - LiveRatio: Based on ActiveDays per period:
    - Daily→Weekly: case(ActiveDays < 3, 'Swift', 'Occasional')
    - Daily→Monthly: case(ActiveDays < 3, 'Swift', ActiveDays < 10, 'Occasional', 'Dedicate')
  - Serverless vs ServerMode: From ConnectionMode_Daily and RPSettingLatest.Extras (e.g., socketIO.serviceMode)

- ID parsing/derivation
  - Description: Extract SubscriptionId and primary resource id; standardize case.
  - Snippet:
    ```kusto
    | extend ResourceId = tolower(ResourceId)
    | parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
    | extend PrimaryResourceId = iif(ResourceId has '/replicas/', substring(ResourceId, 0, indexof(ResourceId, '/replicas/')), ResourceId)
    ```
- Sharded union
  - Description: Merge EU and Non-EU shards of the same schema and normalize keys before aggregate.
  - Snippet:
    ```kusto
    let base =
        RuntimeRequestsGroups_Daily
        | where Date > ago(60d)
    ;
    let base_eu =
        RuntimeRequestsGroups_EU_Daily
        | where Date > ago(60d)
    ;
    union isfuzzy=true base, base_eu
    | extend ResourceId = tolower(ResourceId)
    | summarize ResourceCount = dcount(ResourceId, 3), RequestCount = sum(RequestCount) by Date, Category, Metrics
    ```

- Revenue unit price mapping
  - Description: Abstract SKU→unit price; avoid hardcoding numbers in templates.
  - Snippet:
    ```kusto
    // Replace placeholders with governance-approved values
    let UnitPriceFree = 0.0;
    let UnitPriceStandard = <UnitPriceStandard>;
    let UnitPricePremium = <UnitPricePremium>;
    extend Revenue = case(
        SKU == 'Free',     UnitPriceFree,
        SKU == 'Standard', UnitPriceStandard,
        SKU == 'Premium',  UnitPricePremium,
        0.0
    ) * Quantity
    ```

## Example Queries (with explanations)

1) Daily billable units and revenue (SignalR)
- Description: Summarizes billable unit quantity and revenue per day for SignalR, excludes internal subscriptions, and uses an effective end-day gate based on coverage in two regions. Adapt by changing time window, SKU filter, or adding dimensions.
```kusto
let EndDate = toscalar(BillingUsage_Daily | where Date > ago(10d) and Region in ('australiaeast', 'westeurope') 
| summarize counter = dcount(Region) by Date | where counter >= 2 | top 1 by Date desc | project Date);
BillingUsage_Daily
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds) and Date >= ago(60d) and ResourceId has '/signalr/' and Date <= EndDate
| extend Revenue = case(SKU == 'Free', 0.0, SKU == 'Standard', 1.61, SKU == 'Premium', 2.0, 1.0)*Quantity
| join kind = leftouter SubscriptionMappings on SubscriptionId
| summarize Total = sum(Quantity), Revenue = sum(Revenue) by Date, SKU, CustomerType
```

2) Daily active resource count with connection gate (SignalR)
- Description: Counts distinct resources per day by SKU and region, folding in a connection-activity gate via ResourceMetrics. Uses coverage gate for end day. Adapt to WebPubSub by changing the service filter.
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

3) OKR consumption daily (All services with SKU filter)
- Description: Computes daily consumption across SKUs and pivots by service (SignalR vs WebPubSub) using boolean flags. Excludes internal subscriptions and message-only SKUs. Adapt by editing the 30d window or adding customer segment breakdown.
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
```

4) AI customer monthly growth (brand cohort)
- Description: Builds a 28-day rolling AI cohort based on keywords in ResourceId, compares latest and prior periods, and overlays subscription growth goals. Adapt keywords or period length as needed.
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

5) Weekly AutoScale feature adoption in Premium (SignalR)
- Description: Counts resources using AutoScale and computes its share among Premium resources weekly. Good for feature tracking. Adapt SKUs or service filter to Web PubSub.
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

6) Top subscriptions (SignalR)
- Description: Combines snapshot of top subscriptions with CustomerModel and multiple enrichments (tags, feature signals, connection modes). Useful to drill into external/billable customers and adoption flags. Adapt the 29-day window or joins based on available features.
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

7) Monthly retention by subscription
- Description: Computes cohort retention by month using snapshots with active windows (StartDate..EndDate). Adapt by switching to Customer or Resource snapshots and changing the lookback window.
```kusto
let initTime = datetime_add('year', -1, startofmonth(now()));
range x from 0 to 12 step 1
| extend RangeMonth = datetime_add('month', -1*x, startofmonth(now())), fakeKey = 1
| join kind = inner (SubscriptionRetentionSnapshot 
| where StartDate >= initTime
| extend StartMonth = startofmonth(StartDate), fakeKey = 1) on fakeKey
| extend Periods = datetime_diff('month', RangeMonth, StartMonth)
| where StartMonth <= RangeMonth and EndDate >= RangeMonth
| summarize Retain = dcount(SubscriptionId) by StartMonth, Periods
| join kind = inner (SubscriptionRetentionSnapshot 
| where StartDate >= initTime
| extend StartMonth = startofmonth(StartDate)
| distinct StartMonth, SubscriptionId, EndDate
| summarize Total = dcount(SubscriptionId) by StartMonth) on StartMonth
| extend Category = 'Subscription'
| project Month = StartMonth, Periods, Total, Retain, Ratio = 1.0*Retain/Total, Category
```

8) Weekly resource totals with live ratio (SignalR)
- Description: Builds weekly counts by live ratio categories (‘Swift’, ‘Occasional’) using active day counts from ResourceMetrics. Helps track active cohort distribution. Adapt startofweek window or add HasConnection dimension.
```kusto
BillingUsage_Daily
| where Date >= startofweek(now(), -8) and SubscriptionId !in (SignalRTeamInternalSubscriptionIds()) and ResourceId has 'microsoft.signalrservice/signalr'
| join kind = inner ResourceMetrics on ResourceId, Date
| summarize Conn = max(MaxConnectionCount), SKU = max(SKU), Region = max(Region), ActiveDays = dcount(Date) by Week=startofweek(Date), ResourceId
| project Week, ResourceId, Category = 'Total', Region, SKU, HasConnection = Conn > 0, LiveRatio = case(ActiveDays < 3, 'Swift', 'Occasional')
| summarize ResourceCnt = dcount(ResourceId, 3) by Week, Category, Region, SKU, HasConnection, LiveRatio
```

9) SocketIO serverless percentage (Web PubSub)
- Description: For SocketIO-kind resources, computes the share that run in Serverless mode, weekly, optionally split by SKU and team subscriptions. Adapt the window and add customer filters as needed.
```kusto
let raw = RPSettingLatest
| where ResourceId has '/Microsoft.SignalRService/WebPubSub/' and Kind == 'SocketIO'
| join kind = inner (
    BillingUsage_Daily
    | where Date >= startofweek(now(), -8)
) on ResourceId
| extend IsTeamSubs = iff(SubscriptionId in (SignalRTeamInternalSubscriptionIds), true, false),
        ServiceMode = extract_json('$.socketIO.serviceMode', Extras, typeof(string))
| project Week = startofweek(Date), ResourceId, SKU = SKU1, IsTeamSubs, ServiceMode;
let summaryCounts = raw
| summarize TotalSocketIOResourceCount = dcount(ResourceId) by Week;
let serverlessCounts = raw
| where ServiceMode =~ 'Serverless'
| summarize ServerlessCount = dcount(ResourceId) by Week, SKU, IsTeamSubs;
serverlessCounts
| join kind = inner (summaryCounts) on Week
| extend ServerlessPercentageByAllSkuTotal = 1.0*ServerlessCount / TotalSocketIOResourceCount
| project Week, SKU, ServerlessCount, ServerlessPercentageByAllSkuTotal, IsTeamSubs
```

10) Slicer label for latest complete day
- Description: Produces a label that marks the latest date with multi-region completeness as “Latest”, useful for dashboards. Adapt the region set to your sentinel slices.
```kusto
BillingUsage_Daily
| where Date >= ago(61d) and Region in ('australiaeast', 'westeurope')
| summarize counter = dcount(Region) by Date
| where counter > 1
| sort by Date
| extend Rank = row_rank(Date)
| project Date, SlicerDate = iif(Rank == 1, 'Latest', format_datetime(Date, 'yyyy-MM-dd'))
```

## Reasoning Notes (only if uncertain)

- Timezone: Not explicitly stated; assume UTC because ADX stores datetimes in UTC, and queries use startofday/week/month without tz offsets.
- Internal subscription cohort: SignalRTeamInternalSubscriptionIds appears both as a table/variable and as a function. We keep both patterns as used in queries.
- Revenue unit prices: Values 1.61 (Standard) and 2.0 (Premium) are hardcoded in queries. In building blocks they should be abstracted as placeholders pending finance/governance confirmation.
- “HasConnection” definition: Implemented as MaxConnectionCount > 0 via ResourceMetrics. Adopted because used consistently across active resource queries.
- Replicas handling: Some queries fold replicas by stripping '/replicas/'. Adopt this for de-duplication when counting resources to avoid double counting.
- Completeness gate: Two-region gate (AU East and West Europe) is used as a coverage heuristic. Assumed as baseline; you may expand to additional regions if required for your scenario.
- SocketIO service mode: Extracted from RPSettingLatest.Extras JSON; treat ServiceMode =~ 'Serverless' as serverless. Other modes may exist; tune as needed.

## Canonical Tables

Important notes
- Schema lookup: The ADX schema tool isn’t available for this product in this environment. Table columns below are compiled from actual query usage in the provided content. Treat them as the minimal required columns; the physical schema may include more fields.
- Freshness: Most “Daily” tables are day-partitioned and refreshed daily; “Weekly”/“Monthly” are pre-aggregated snapshots. Exact ingestion delay and timezone are unknown; avoid using “today” unless you explicitly handle partial data.
- Common filters and joins:
  - Time: Date > ago(Xd), or startofweek/startofmonth windows
  - Service filter: ResourceId has 'microsoft.signalrservice/signalr' or contains '/webpubsub/'
  - Internal exclusion: SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
  - Product joins: SubscriptionMappings (enrich to CustomerType, BillingType, SegmentName, CloudCustomerGuid), RPSettingLatest for SKU/Kind/Extras, ResourceMetrics for connections/messages

Order: High-priority tables first, then Normal, then Low.

---

### Table: Cached_SubsTotalWeekly_Snapshot (SignalR/WebPubSub)
- Priority: High
- What this table represents: Weekly snapshot for subscriptions and customers with enriched dimensions. Pre-aggregated counts for trend and top-level OKR.
- Freshness expectations: Weekly aggregates; latest complete week only.
- When to use:
  - Weekly subscription/customer totals and segmentation (Region, SKU, OfferType/Name, BillingType, LiveRatio).
  - Top customers and growth WoW with stable weekly boundaries.
- When to avoid:
  - Per-day billing totals (use BillingUsage_Daily).
  - Real-time operational connection/message counts (use ResourceMetrics).
- Similar tables & how to choose:
  - Cached_SubsTotalMonthly_Snapshot: monthly roll-up; choose per reporting cadence.
  - Cached_CustomerFlow_Snapshot: cohort movements/flow by week/month.
- Common Filters:
  - Week time window, ServiceType in ('SignalR','WebPubSub'), join to SubscriptionMappings for CustomerType/SegmentName.
- Table columns (from queries):
  | Column        | Type    | Description or meaning |
  |---------------|---------|------------------------|
  | Week          | datetime| Week bucket (startofweek) |
  | ServiceType   | string  | 'SignalR' or 'WebPubSub' |
  | Region        | string  | Azure region |
  | OfferType     | string  | Commerce offer type |
  | OfferName     | string  | Offer name |
  | BillingType   | string  | e.g., 'Internal', 'External' |
  | SKU           | string  | Free/Standard/Premium |
  | CustomerType  | string  | From SubscriptionMappings |
  | HasConnection | bool    | Any connections observed |
  | LiveRatio     | string  | Swift/Occasional/Dedicate-like categories |
  | SubscriptionId| string  | Used for enrichment joins |
  | CloudCustomerGuid | string | For dcount CustomerCnt |
- Column explain:
  - Week: primary time grain.
  - SKU/BillingType/CustomerType/Region: segmentation pivots.
  - HasConnection/LiveRatio: activity/quality segmentation for resources tied to the subscription.

---

### Table: Cached_SubsTotalMonthly_Snapshot (SignalR/WebPubSub)
- Priority: High
- What this table represents: Monthly snapshot for subscriptions/customers with rich dimensions; stable month boundaries for OKR and cohort reporting.
- Freshness: Monthly aggregates; avoid including current in-progress month without normalization.
- When to use:
  - Subscription/customer totals monthly.
  - Executive and OKR reporting by month.
- When to avoid:
  - Daily/weekly analysis (use weekly snapshot or BillingUsage_Daily/ResourceMetrics).
- Similar tables: Cached_SubsTotalWeekly_Snapshot (weekly). Choose based on granularity.
- Common Filters:
  - Month range; ServiceType; join SubscriptionMappings.
- Table columns:
  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Month         | datetime | Month bucket |
  | ServiceType   | string   | 'SignalR'/'WebPubSub' |
  | Region        | string   | Azure region |
  | OfferType     | string   | Offer type |
  | OfferName     | string   | Offer name |
  | BillingType   | string   | Usage type (Internal/External etc.) |
  | SKU           | string   | Free/Standard/Premium |
  | CustomerType  | string   | From mappings |
  | HasConnection | bool     | Activity flag |
  | LiveRatio     | string   | Live-ness category |
  | SubscriptionId| string   | For joins |
  | CloudCustomerGuid | string | For customer counts |
- Column explain:
  - Month: primary time grain.
  - Dimensions identical to weekly counterpart; prefer monthly when producing month-cadence KPIs.

---

### Table: Cached_CustomerFlow_Snapshot
- Priority: High
- What this table represents: Precomputed cohort flow/transition data for customers across periods.
- Freshness: Stored as periodic snapshots; choose weekly/monthly via Partition or use separate CustomerFlow_Weekly/Monthly functions.
- When to use:
  - Customer flow/cohort changes over time (e.g., new, retained).
- When to avoid:
  - Raw dcount of customers per day (use BillingUsage_Daily + SubscriptionMappings).
- Similar tables: CustomerFlow_Weekly/Monthly functions; pick snapshot vs function depending on need for parameters.
- Common Filters: ServiceType ('SignalR'), Partition ('Week'/'Month'), then rename Date to Week/Month.
- Table columns:
  | Column      | Type     | Description |
  |-------------|----------|-------------|
  | Date        | datetime | Period date; rename to Week/Month |
  | ServiceType | string   | 'SignalR' or 'WebPubSub' |
  | Partition   | string   | 'Week' or 'Month' |
  | (flow dims) | string   | Flow category fields (as provided in snapshot) |
- Column explain:
  - Partition sets granularity; use Date as the target period label.

---

### Table: FeatureTrackV2_Daily
- Priority: High
- What this table represents: Daily feature usage signal (RequestCount by Feature/Category/Resource).
- Freshness: Daily; EU data also recorded in FeatureTrackV2_EU_Daily (union for global view).
- When to use:
  - Feature adoption tracking (e.g., Samples, Ping categories).
  - Assessing SKU engagement for features (join BillingUsage_Daily).
- When to avoid:
  - Operational QoS (use OperationQoS_Daily/ConnectivityQoS_Daily).
- Similar tables: FeatureTrackV2_EU_Daily (regional shard), FeatureTrack_Daily (legacy).
- Common Filters:
  - Date window; ResourceId contains '/signalr/' or '/webpubsub/'.
  - Exclude team subs; join BillingUsage_Daily for SKU.
- Table columns:
  | Column       | Type     | Description |
  |--------------|----------|-------------|
  | Date         | datetime | Event date (startofday used in joins) |
  | Feature      | string   | Feature name (e.g., BlazorServerSide, Subprotocol) |
  | Category     | string   | Derived category (sometimes parsed from Category field) |
  | ResourceId   | string   | Azure resource ID |
  | SubscriptionId | string | Often derived via split(ResourceId,'/')[2] |
  | RequestCount | long     | Count of requests attributed to feature |
  | Properties   | dynamic  | Extra props (often projected away) |
- Column explain:
  - Feature/Category: core breakdown for adoption; used to compute counts per Week.
  - ResourceId/SubscriptionId: join keys to BillingUsage_Daily.

---

### Table: FeatureTrackV2_EU_Daily
- Priority: High
- What this table represents: EU-sharded counterpart to FeatureTrackV2_Daily; union both for complete global coverage.
- Freshness: Daily; same caveats as FeatureTrackV2_Daily.
- When to use: Same as above, when EU data needed.
- Similar tables: FeatureTrackV2_Daily.
- Common Filters: Same as FeatureTrackV2_Daily.
- Table columns: Same as FeatureTrackV2_Daily.

---

### Table: FeatureTrack_Daily
- Priority: High
- What this table represents: Daily feature signals (earlier/alternative feed to V2).
- Freshness: Daily.
- When to use:
  - Specific features (ServerSticky, ConnectionCountLimitReached, MultiEndpoints, Upstream_Exceptions).
- When to avoid:
  - EU unioning (prefer FeatureTrackV2 + EU table).
- Similar: FeatureTrackV2_Daily (preferred for breadth).
- Common Filters: Date, ResourceId contains service, exclude team subs.
- Table columns:
  | Column       | Type     | Description |
  |--------------|----------|-------------|
  | Date         | datetime | Event date |
  | Feature      | string   | Feature name |
  | RequestCount | long     | Requests tied to feature |
  | ResourceId   | string   | Resource ID |
- Column explain:
  - Feature: used to derive boolean flags (ServerSticky, NeededScale).
  - ResourceId: join to SubscriptionId via split for enrichment.

---

### Table: FeatureTrack_AutoScale_Daily
- Priority: High
- What this table represents: Feature usage for autoscale scenarios per resource/day.
- Freshness: Daily.
- When to use:
  - Count of resources with auto-scale features, ratio vs Premium resources.
- When to avoid:
  - General feature adoption (use FeatureTrackV2/FeatureTrack_Daily).
- Similar: FeatureTrack_Daily (for other features).
- Common Filters: Date window, exclude team subs, require ResourceId has service, often joined to BillingUsage_Daily filtered to SKU == 'Premium'.
- Table columns:
  | Column     | Type     | Description |
  |------------|----------|-------------|
  | Date       | datetime | Event date |
  | ResourceId | string   | Resource using autoscale-related feature |
- Column explain:
  - Used for resource-level dcount per week.

---

### Table: RuntimeResourceTags_Daily
- Priority: High
- What this table represents: Daily runtime flags/tags per subscription or resource (e.g., IsAppService, IsProxy, IsStaticApps; sample usage flags).
- Freshness: Daily.
- When to use:
  - Enrich top subscriptions with runtime environment flags.
  - Identify sample usage for WebPubSub.
- When to avoid:
  - Billing or connection counts (use BillingUsage_Daily/ResourceMetrics).
- Similar: RPSettingLatest (static metadata).
- Common Filters: Date window; ServiceType filter; group by SubscriptionId.
- Table columns:
  | Column        | Type    | Description |
  |---------------|---------|-------------|
  | Date          | datetime| Day |
  | ServiceType   | string  | 'SignalR'/'WebPubSub' |
  | SubscriptionId| string  | Subscription key |
  | IsAppService  | bool    | App Service detected |
  | IsProxy       | bool    | Using proxy |
  | IsStaticApps  | bool    | Using Static Web Apps |
  | IsSample      | bool    | Sample usage flag (used in WebPubSub features query) |
- Column explain:
  - Use as boolean enrichers when profiling top subscriptions.

---

### Table: SubscriptionFlow_Weekly
- Priority: High
- What this table represents: Function/view result producing weekly subscription flow (parameters for start/end; used as a logical table).
- Freshness: Computed at query time from latest underlying snapshots.
- When to use: Subscription cohort/flow analysis at weekly grain for WebPubSub.
- When to avoid: Static point-in-time totals (use Cached_SubsTotalWeekly_Snapshot).
- Similar: SubscriptionFlow_Monthly; Cached_SubscriptionFlow_Snapshot (snapshot).
- Common Filters: Week >= boundary date; parameters: startDate, endDate, serviceType flag (implicit).
- Table columns (logical):
  | Column | Type     | Description |
  |--------|----------|-------------|
  | Week   | datetime | Week bucket |
  | (flow dimensions) | string | Flow category columns |
- Column explain:
  - Use to categorize adds/churn/retention by week.

---

### Table: SubscriptionFlow_Monthly
- Priority: High
- Same as weekly but month grain.
- Columns: Month (datetime) + flow dimensions.

---

### Table: CustomerFlow_Weekly
- Priority: High
- Weekly customer flow/cohort function.
- Columns: Week (datetime) + flow dimensions.

---

### Table: CustomerFlow_Monthly
- Priority: High
- Monthly customer flow/cohort function.
- Columns: Month (datetime) + flow dimensions.

---

### Table: CustomerModel
- Priority: High
- What this table represents: Enriched customer/subscription metrics model for “Top subscriptions” pages.
- Freshness: Snapshot; exact cadence not specified.
- When to use:
  - Pre-joined customer KPIs: Revenue, MaxConnection, MessageCount, Rate and identifiers/names (CloudCustomerName, TPName, P360_ID/TPID).
- When to avoid:
  - Time series trends (use TopSubscriptionsTrends style queries with ResourceMetrics and BillingUsage_Daily).
- Similar: Cached_TopSubscriptions_Snapshot (not listed but used by queries for time series).
- Common Filters: Service == 'SignalR' or 'WebPubSub' (when used via snapshots and then join to CustomerModel).
- Table columns (from usage):
  | Column           | Type    | Description |
  |------------------|---------|-------------|
  | SubscriptionId   | string  | Key for joins |
  | Revenue          | real    | Revenue aggregate |
  | MaxConnection    | long    | Max connections (agg) |
  | MessageCount     | long    | Messages (agg) |
  | Rate             | real    | Model score or rate |
  | CloudCustomerName| string  | Display name |
  | CustomerType     | string  | Internal/External |
  | TPName           | string  | Tenant/TP name |
  | BillingType      | string  | Billing segmentation |
  | OfferName        | string  | Offer label |
  | OfferType        | string  | Offer type |
  | P360_ID, TPID    | string  | Customer IDs (C360/TP) |
- Column explain:
  - Identifiers enable linking to C360; metric columns power top list ranking.

---

### Table: KPI_SocketIO
- Priority: High
- What this table represents: KPI time series for Socket.IO variant.
- Freshness: KPI pipeline-driven; unknown daily cadence.
- When to use: KPI trend lines and OKR pivot for Socket.IO.
- Columns (from usage):
  | Column | Type     | Description |
  |--------|----------|-------------|
  | (Date) | datetime | Time axis (in KPI queries) |
  | (Category)| string| KPI dimension |
  | (Value)| real     | KPI numeric value |
- Column explain:
  - Category/Value pair used with pivot to build KPI panels.

---

## Normal Priority Tables

### Table: Cached_ZnOKRARR_Snapshot
- Priority: Normal
- Represents: Snapshot of ARR OKR series for SignalR with appended goals via fullouter join to datatable goals.
- Freshness: Snapshot-style; unknown cadence.
- Use: Plot actual vs goal for ARR by month.
- Common Filters: Join on TimeStamp to static goals.
- Columns:
  | Column    | Type     | Description |
  |-----------|----------|-------------|
  | TimeStamp | datetime | Month end |
  | (ARR fields)| real   | ARR metrics |
- Column explain: TimeStamp is the join key to goal series.

### Table: MaxConnectionCount_Daily
- Priority: Normal
- Represents: Daily activity presence check (exists/has data) and per SubscriptionId presence for resource activity.
- Freshness: Daily.
- Use: Existence joins to BillingUsage_Daily to filter active resources/subs; sometimes joins on Role and Date.
- Common Filters: Date windows; summarize count() by Date, SubscriptionId.
- Columns:
  | Column       | Type     | Description |
  |--------------|----------|-------------|
  | Date         | datetime | Day bucket |
  | SubscriptionId | string | Join key |
  | Role         | string   | Lower-cased role (used in some joins) |
- Column explain: Used to confirm active usage on a date before counting.

### Table: BillingUsage_Daily
- Priority: Normal
- Represents: Daily billing usage records (Quantity by ResourceId/SKU); base for revenue and paid unit computations.
- Freshness: Daily; current day may be partial.
- Use:
  - Revenue and paid unit trends (Quantity * <UnitPriceSKU>).
  - Filter by SKU (Free/Standard/Premium) and by service type via ResourceId.
  - Cohort/AI subsets with ResourceId text filters (gpt/ai/ml/cognitive/openai/chatgpt).
- Avoid:
  - Connection/message telemetry (use ResourceMetrics).
- Similar: Cached_SubsTotal* for pre-aggregated counts; choose BillingUsage_Daily for flexibility and custom aggregation.
- Common Filters:
  - Date ranges, SubscriptionId !in (SignalRTeamInternalSubscriptionIds), SKU filters, ResourceId service filter, Region filters.
- Columns:
  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Date          | datetime | Day |
  | SubscriptionId| string   | Billing subscription |
  | ResourceId    | string   | Azure resource path |
  | SKU           | string   | Free/Standard/Premium/MessageCount(...) |
  | Quantity      | real     | Usage units |
  | Region        | string   | Azure region |
- Column explain:
  - SKU and Quantity used to compute revenue and paid units; ResourceId used to identify product type; SubscriptionId to enrich with mappings.

### Table: SubscriptionMappings
- Priority: Normal
- Represents: Subscription-level enrichment (CustomerType, BillingType, SegmentName, CloudCustomerGuid).
- Freshness: Updated as subscription mapping changes; not strictly daily.
- Use: Always join on SubscriptionId to classify customers and segments.
- Columns:
  | Column           | Type   | Description |
  |------------------|--------|-------------|
  | SubscriptionId   | string | Join key |
  | CustomerType     | string | Internal/External |
  | BillingType      | string | Billing class when not Internal |
  | SegmentName      | string | Segmentation label |
  | CloudCustomerGuid| string | Customer identifier |
- Column explain: Use CustomerType when deriving UsageType; SegmentName for slicing OKRs.

### Table: Cached_ZnOKREstRevenueWeekly_Snapshot / Cached_ZnOKREstRevenueMonthly_Snapshot
- Priority: Normal
- Represents: Estimated revenue OKR snapshots at weekly/monthly grains.
- Use: OKR panels for SignalR with goal jo ins.
- Columns:
  | Column    | Type     | Description |
  |-----------|----------|-------------|
  | TimeStamp | datetime | Period end |
  | (Revenue fields)| real| Estimated revenue values |

### Table: Cached_ZnOKRSubs_Snapshot
- Priority: Normal
- Represents: Subscription OKR snapshot with appended WebPubSub goals.
- Use: Goal tracking for SignalR subscriptions.
- Columns: TimeStamp (datetime), WebPubSubGoal/WebPubSubGrowthGoal (real), plus subscription counts.

### Table: OKRv2021
- Priority: Normal
- Represents: KPI/OKR category/value series (Date, Category, Value).
- Use: Pivot(Category,sum(Value)) to KPI panels.
- Columns: Date (datetime), Category (string), Value (real).

### Table: Cached_CuOKRConsumption_*(Snapshot/Weekly/Monthly)
- Priority: Normal
- Represents: Consumption OKR snapshots with goals; actuals often derived from BillingUsage_Daily.
- Columns: TimeStamp (datetime), ConsumptionGoal/GrowthGoal/SignalRGoal/... (real).

### Table: ResourceMetrics
- Priority: Normal
- Represents: Daily per-resource telemetry aggregates (MaxConnectionCount, SumMessageCount, AvgConnectionCount) with Region.
- Freshness: Daily.
- Use:
  - Service usage panels (connections/messages).
  - Counting active resources and activity flags (HasConnection).
- Avoid: Billing computations (use BillingUsage_Daily).
- Similar: ConnectionMode_Daily (mode-specific counts).
- Common Filters: Date windows; ResourceId service filter; parse SubscriptionId from ResourceId for joins.
- Columns:
  | Column            | Type     | Description |
  |-------------------|----------|-------------|
  | Date              | datetime | Day |
  | ResourceId        | string   | Resource path |
  | MaxConnectionCount| long     | Peak connections per resource/day |
  | SumMessageCount   | long     | Total messages |
  | AvgConnectionCount| long     | Average connections |
  | Region            | string   | Region |
- Column explain:
  - MaxConnectionCount and SumMessageCount are core usage KPIs; Region to segment; join with RPSettingLatest and mappings.

### Table: RPSettingLatest
- Priority: Normal
- Represents: Latest RP-discovered metadata for resources (Kind, ServiceMode, Extras JSON).
- Freshness: On config change.
- Use: Enrich ResourceId to Kind (WebPubSub/SocketIO), ServiceMode, flags (e.g., Extras has 'isAspire').
- Columns:
  | Column     | Type    | Description |
  |------------|---------|-------------|
  | ResourceId | string  | Resource key |
  | Kind       | string  | 'WebPubSub', 'SocketIO', etc. |
  | ServiceMode| string  | e.g., 'Default','Serverless' (sometimes parsed from Extras) |
  | Extras     | dynamic | JSON metadata |
- Column explain:
  - Use extract_json('$.socketIO.serviceMode', Extras, typeof(string)) for SocketIO service mode.

### Table: ManageResourceTags
- Priority: Normal
- Represents: Management-plane (ARM) request aggregations per Date/Resource/Subscription (RequestName, Tags).
- Use: Method mix analysis (e.g., provisioning patterns).
- Columns:
  | Column       | Type     | Description |
  |--------------|----------|-------------|
  | Date         | datetime | Day |
  | RequestName  | string   | Operation name |
  | Tags         | string   | Request method/tag (used as RequestMethod) |
  | SubscriptionId| string  | Join key |
  | ResourceId   | string   | Resource |
  | Count        | long     | Count of operations |
- Column explain: Summarize OperationCount, then join mappings for CustomerType.

### Table: ConnectionMode_Daily
- Priority: Normal
- Represents: Daily connection mode metrics (Serverless vs Proxy/ServerMode).
- Use: Mode breakdown and connection totals per day.
- Columns:
  | Column              | Type     | Description |
  |---------------------|----------|-------------|
  | Date                | datetime | Day |
  | ResourceId          | string   | Resource |
  | ServiceMode         | string   | e.g., 'Default' |
  | ServerlessConnection| long     | Count of serverless conn |
  | ProxyConnection     | long     | Count of server mode conn |
- Column explain: Used to derive IsServerless/IsServerMode per subscription.

### Table: KPIv2019 / KPI_AWPS / OKRv2021_AWPS / OKRv2021_SocketIO
- Priority: Normal
- Represents: Historical KPI series; union with SocketIO-specific KPI for AWPS.
- Columns: Date (datetime), Category (string), Value (real).

### Table: ChurnCustomers_Monthly
- Priority: Normal
- Represents: Monthly churn table; picking latest run per month using RunDay.
- Use: SignalR/WebPubSub churn rates.
- Columns:
  | Column             | Type     | Description |
  |--------------------|----------|-------------|
  | Month              | datetime | Month bucket |
  | RunDay             | datetime | ETL run day |
  | ServiceType        | string   | Product |
  | StandardChurn      | long     | Churned standard count |
  | Standard           | long     | Standard base |
  | Churn              | long     | Total churn |
  | Total              | long     | Total base |
- Column explain: Used to compute churn rates per month.

### Table: ConvertCustomer_Weekly
- Priority: Normal
- Represents: Weekly conversions (Free->Paid/Standard/Premium, Standard->Premium).
- Columns: Week (datetime), RunDay (datetime), ServiceType, FreeToPaid, FreeToStandard, FreeToPremium, StandardToPremium.

### Table: DeleteSurvey / DeleteSurveyWebPubSub
- Priority: Normal
- Represents: Deletion survey responses.
- Columns: TIMESTAMP, Deployment, resourceId, reason, feedback.

### Table: SubscriptionRetentionSnapshot / CustomerRetentionSnapshot / ResourceRetentionSnapshot
- Priority: Normal
- Represents: Snapshots for retention cohort analysis with StartDate/EndDate windows.
- Use: Cohort retention matrices (retain vs total per period).
- Columns:
  | Column       | Type     | Description |
  |--------------|----------|-------------|
  | StartDate    | datetime | Cohort start |
  | EndDate      | datetime | Retain window end |
  | SubscriptionId/C360_ID/ResourceId | string | Entity id |

### Table: Cached_ResourceFlow_Snapshot
- Priority: Normal
- Represents: Resource cohort flow snapshot; filter Partition 'Week'/'Month', ServiceType.
- Columns: Date (datetime), ServiceType (string), Partition (string), plus flow metrics.

### Table: ResourceFlow_Weekly / ResourceFlow_Monthly (functions)
- Priority: Normal
- Represents: Parameterized cohort flow for resources.
- Columns: Week/Month (datetime), flow dimensions.

---

## Low Priority Tables

### Table: OperationQoS_Daily
- Priority: Low
- Represents: Daily operations uptime (totalUpTimeSec/totalTimeSec) per env role/location.
- Use: QoS daily/rolling/weekly/monthly, SLA attainment.
- Columns:
  | Column          | Type     | Description |
  |-----------------|----------|-------------|
  | env_time        | datetime | Time |
  | env_cloud_location | string| Region |
  | env_cloud_role  | string   | Resource/role |
  | resourceId      | string   | Resource id |
  | totalTimeSec    | long     | Period seconds |
  | totalUpTimeSec  | long     | Uptime seconds |
- Column explain: Compute Qos = sum(UpTime)/sum(Total).

### Table: ConnectivityQoS_Daily
- Priority: Low
- Represents: Connectivity uptime variant; same structure; SLA threshold differs (0.995 commonly).
- Columns: Same as OperationQoS_Daily.

### Table: ManageRPQosDaily
- Priority: Low
- Represents: Management-plane QoS by API (success/timeout/customer error).
- Use: Daily/rolling/weekly/monthly management QoS panels.
- Columns:
  | Column      | Type     | Description |
  |-------------|----------|-------------|
  | Date        | datetime | Day |
  | Region      | string   | Region |
  | ApiName     | string   | API action |
  | Count       | long     | Requests count |
  | Result      | string   | Result category |
  | CustomerType| string   | Product family filter ('SignalR','WebPubSub','') |
  | SubscriptionId | string| For some joins |
- Column explain: Qos computed as sumif(Count,Result in (...) )/sum(Count).

### Table: RuntimeRequestsGroups_Daily / RuntimeRequestsGroups_EU_Daily
- Priority: Low
- Represents: Grouped runtime requests by Category/Metrics (RestApiScenario, etc.).
- Use: High-level traffic volumes and patterns; EU shard unioned.
- Columns:
  | Column      | Type     | Description |
  |-------------|----------|-------------|
  | Date        | datetime | Day |
  | Category    | string   | Scenario category |
  | Metrics     | string   | Metric key (sometimes normalized) |
  | ResourceId  | string   | Resource (may not always present) |
  | RequestCount| long     | Requests |
  | ResourceCount| long    | Distinct resources |
- Column explain: Metrics normalized for HubProxy or v2021 formatting.

### Table: RuntimeTransport_Daily / RuntimeTransport_EU_Daily
- Priority: Low
- Represents: Runtime transport usage by Framework-Transport pairs.
- Columns:
  | Column    | Type     | Description |
  |-----------|----------|-------------|
  | Date      | datetime | Day |
  | Framework | string   | SDK/runtime |
  | Transport | string   | WebSocket/LongPolling/etc. |
  | ResourceId| string   | Resource |
  | RequestCount | long  | Requests |
- Column explain: Combined Metrics via strcat(Framework,'-',Transport) in queries.

### Table: ConnectionMode_Daily (listed above as Normal) — already covered.

### Table: KPI (KPIv2019) — already covered in Normal.

### Table: ConvertCustomer_Weekly / ChurnCustomers_Monthly — covered in Normal.

### Table: WebTools_Raw (ddtelinsights cluster)
- Priority: Low
- What this represents: Visual Studio telemetry for SignalR detection, publish events, provisioning flows.
- Cross-source: cluster ddtelinsights (database unknown).
- Use: Developer funnel analysis (publish, dependencies state, provisioning).
- Common Filters: AdvancedServerTimestampUtc windows, EventName patterns; ExeVersion filtering; dynamic fields in Properties/Measures.
- Table columns:
  | Column                    | Type     | Description |
  |---------------------------|----------|-------------|
  | AdvancedServerTimestampUtc| datetime | Event time |
  | EventName                 | string   | Telemetry event ID |
  | Properties                | dynamic  | Key-value bag |
  | Measures                  | dynamic  | Numeric bag |
  | ExeVersion                | string   | VS version |
  | MacAddressHash            | string   | Device id hash |
  | ActiveProjectId           | string   | Project id |
- Column explain: Properties/Measures used to derive states like Suggested/Added/Missing; SubscriptionId parsed from URIs.

### Table: Unionizer('Requests','HttpIncomingRequests') (armprodgbl.eastus)
- Priority: Low
- What this represents: Cross-cluster unionized ARM request telemetry (Requests + HttpIncomingRequests).
- Use: ARM activity impacting SignalR EventGrid filters.
- Columns (from usage):
  | Column                 | Type     | Description |
  |------------------------|----------|-------------|
  | TIMESTAMP              | datetime | Event time |
  | targetResourceProvider | string   | 'MICROSOFT.SIGNALRSERVICE' |
  | httpMethod             | string   | PUT/DELETE etc. |
  | targetResourceType     | string   | 'SIGNALR/EVENTGRIDFILTERS' |
  | subscriptionId         | string   | ARM subscription |
  | targetUri              | string   | Full ARM URI |
  | SourceNamespace        | string   | Source namespace |
- Column explain: Used to derive ResourceId and action, and Location from SourceNamespace.

### Table: AwpsRuntimeRequestsGroups_Daily
- Priority: Low
- Represents: WebPubSub-specific runtime request groupings with normalized Metrics (v2021-…).
- Columns: Date, Category, Metrics.

---

## Additional Normal-Priority Tables (OKRs and Labels)
- Cached_ZnOKRSubsWeekly_Snapshot / Cached_ZnOKRSubsMonthly_Snapshot: Subscription OKR snapshots at weekly/monthly grains.
- Cached_DtOKRARR_Snapshot / Cached_DtOKREstRevenueWeekly_Snapshot / Cached_DtOKREstRevenueMonthly_Snapshot: “Dt” variants of ARR/revenue snapshots.
- Cached_DtOKRSubsWeekly_Snapshot / Cached_DtOKRSubsMonthly_Snapshot: “Dt” subscription OKR snapshots.
- KPI_SocketIO (covered as high), OKR_AWPS_SocketIO: SocketIO goals series (Date, goals).
- Label tables: Queries derive date slicers from BillingUsage_Daily; SubscriptionMappings | distinct SegmentName provides segments.

Common filters and patterns across these:
- Join to goal datatables using TimeStamp/Date.
- Prefer startofweek/startofmonth normalization before distinct/pivot.
- Use row_number to keep latest RunDay per Month/Week for churn/convert tables.

---

## Column-use playbook (cross-cutting)
- ResourceId: Core discriminator; use contains/has to split 'signalr' vs 'webpubsub'. For replicas, strip '/replicas/' suffix when deduplicating resource counts.
- SubscriptionId: Always enriched with SubscriptionMappings to get CustomerType, BillingType, SegmentName, CloudCustomerGuid.
- SKU: Use 'in' filters with Free/Standard/Premium and exclude MessageCount when computing revenue/paid units. Revenue = Quantity * <UnitPriceSKU> (use placeholders for SKU unit prices).
- Date grain: Compute Week=startofweek(Date) and Month=startofmonth(Date). Avoid comparing daily to weekly without proper aggregation.
- Activity presence: Join with MaxConnectionCount_Daily or ResourceMetrics to ensure resources were active on a period before counting.

---

Accessibility note
- Direct schema retrieval via ADX tool was not available for this product/cluster. Column lists were inferred strictly from the provided queries and may be incomplete. If you have ADX access, validate with: <table> | getschema on signalrinsights.eastus2/SignalRBI, and for cross-cluster sources (ddtelinsights, armprodgbl.eastus) run equivalent getschema in their respective clusters.