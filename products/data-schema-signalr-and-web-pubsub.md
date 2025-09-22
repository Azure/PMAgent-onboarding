# SignalR and Web PubSub - Product and Data Overview Template

## 1. Product Overview

SignalR and Web PubSub telemetry and business reporting for PMAgent. This product schema focuses on enabling OKR/ARR tracking and core usage analytics across Azure SignalR Service and Azure Web PubSub, including:
- OKR analysis (ARR, subscription/consumption goals)
- AI customer growth cohorts
- Usage KPIs (Revenue, Connection count, Message count)
- Service type growth (SignalR/WebPubSub/SocketIO)
- Feature tracking (replicas, auto-scale, Blazor Server, Aspire)
- External and billable customers focus; exclusion of internal subscriptions
- Top customers reporting
- Labels and retention snapshots
- QoS/Manage/Runtime metrics and VS integration blocks

Conservative time windows and multi-region completeness gates are applied to ensure data completeness, with explicit exclusion of internal/team subscriptions where appropriate.

## 2. Data Platform Overview

- Data Storage: Azure Data Explorer (ADX)
- Product:
  SignalR and Web PubSub
- Product Nick Names: 
  [TODO]Data_Engineer: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations. (Examples to consider: ASRS, SignalR, WebPubSub, WPS, AWPS)
- Kusto Cluster:
  signalrinsights.eastus2
- Kusto Database:
  SignalRBI
- Access Control:
  [TODO] Data Engineer: If this product’s data has high confidentiality concerns, please specify the allowed groups/users here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

# Kusto Query Playbook

This section captures the critical data inventory and KQL snippets used for PMAgent-driven analyses. Content below is provided without changes to preserve exact query semantics used in production reports and dashboards.

## Data Tables (Inventory)

- BillingUsage_Daily  | cluster('signalrinsights.eastus2').database('SignalRBI') | Priority: High
- MaxConnectionCount_Daily  | cluster('signalrinsights.eastus2').database('SignalRBI') | Priority: High
- SubscriptionMappings  | cluster('signalrinsights.eastus2').database('SignalRBI') | Priority: High
- ResourceMetrics  | cluster('signalrinsights.eastus2').database('SignalRBI') | Priority: High
- FeatureTrackV2_Daily  | cluster('signalrinsights.eastus2').database('SignalRBI') | Priority: High
- FeatureTrackV2_EU_Daily  | cluster('signalrinsights.eastus2').database('SignalRBI') | Priority: High
- FeatureTrack_AutoScale_Daily  | cluster('signalrinsights.eastus2').database('SignalRBI') | Priority: High
- Cached_TopSubscriptions_Snapshot  | cluster('signalrinsights.eastus2').database('SignalRBI') | Priority: High
- Cached_ZnOKRARR_Snapshot  | cluster('signalrinsights.eastus2').database('SignalRBI') | Priority: High
- OperationQoS_Daily  | cluster('signalrinsights.eastus2').database('SignalRBI') | Priority: Low
- RuntimeRequestsGroups_Daily  | cluster('signalrinsights.eastus2').database('SignalRBI') | Priority: Low
- RuntimeRequestsGroups_EU_Daily  | cluster('signalrinsights.eastus2').database('SignalRBI') | Priority: Low

## Queries

```kusto
// Effective end date based on multi-region completeness
let GateRegions = dynamic(['australiaeast','westeurope']);
let EndDate =
  toscalar(
    BillingUsage_Daily
    | where Date > ago(10d) and Region in (GateRegions)
    | summarize RegionCnt = dcount(Region) by Date
    | where RegionCnt >= array_length(GateRegions)
    | top 1 by Date desc
    | project Date
  );
// Use complete weeks/months relative to current latest Date in facts
let Current = toscalar(BillingUsage_Daily | top 1 by Date desc | project Date);
let FromWeek = datetime_add('week', -8, startofweek(Current));
let ToWeek = startofweek(Current); // exclusive
let FromMonth = datetime_add('month', -12, startofmonth(Current));
let ToMonth = startofmonth(Current); // exclusive
```

```kusto
let base =
  BillingUsage_Daily
  | where Date between (ago(60d) .. EndDate)
  | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
  | extend ResourceId = tolower(ResourceId)
  | extend IsSignalR = ResourceId has 'microsoft.signalrservice/signalr',
           IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub';
base
| join kind=inner (
    MaxConnectionCount_Daily
    | where Date between (ago(60d) .. EndDate)
    | extend ResourceId = tolower(Role) // Role contains ResourceId
    | summarize count() by Date, ResourceId
  ) on Date, ResourceId
| join kind=leftouter SubscriptionMappings on SubscriptionId
| project-away ResourceId1, Role
```

```kusto
// Collapse replicas to primary resource path
| extend PrimaryResourceId = iif(ResourceId has '/replicas/', substring(ResourceId, 0, indexof(ResourceId, '/replicas/')), ResourceId)
// De-duplicate by latest time per key
| summarize arg_max(Date, *) by PrimaryResourceId
```

```kusto
// Exclude internal team subscriptions
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)

// Exclude non-billable pre-aggregated SKUs if needed
| where SKU !in ('MessageCount','MessageCountPremium')

// Service filters
| extend IsSignalR = ResourceId has 'microsoft.signalrservice/signalr'
| extend IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub'

// AI cohort
| where ResourceId has 'gpt' or ResourceId has 'ai' or ResourceId has 'ml' or ResourceId has 'cognitive'
    or ResourceId contains 'openai' or ResourceId contains 'chatgpt'
```

```kusto
| extend HasConnection = MaxConnectionCount > 0
| extend LiveRatio = case(ActiveDays < 3, 'Swift', ActiveDays < 10, 'Occasional', 'Dedicate')
| extend UsageType = iif(CustomerType == 'Internal', 'Internal', BillingType)
```

```kusto
let UnitPrice_Free = 0.0;
let UnitPrice_Standard = <UnitPriceStandard>; // e.g., 1.61
let UnitPrice_Premium = <UnitPricePremium>;   // e.g., 2.0
let UnitPrice_Default = <UnitPriceDefault>;
| extend Revenue = case(
    SKU == 'Free', UnitPrice_Free * Quantity,
    SKU == 'Standard', UnitPrice_Standard * Quantity,
    SKU == 'Premium', UnitPrice_Premium * Quantity,
    UnitPrice_Default * Quantity)
```

```kusto
| extend ResourceId = tolower(ResourceId)
| parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
// Alternative for split:
| extend SubscriptionId = tostring(split(ResourceId, '/')[2])
```

```kusto
let rr =
  RuntimeRequestsGroups_Daily
  | where Date > ago(60d) and Category != 'Transport'
  | project Date, Category, Metrics, ResourceId, RequestCount, ResourceCount;
let rr_eu =
  RuntimeRequestsGroups_EU_Daily
  | where Date > ago(60d) and Category != 'Transport'
  | project Date, Category, Metrics, ResourceId, RequestCount, ResourceCount;
rr
| union rr_eu
| extend ResourceId = tolower(ResourceId), Date = startofday(Date)
| summarize ResourceCount = dcount(ResourceId), RequestCount = sum(RequestCount) by Date, Category, Metrics
```

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

```kusto
let raw = BillingUsage_Daily
| where Date >= ago(30d) and SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| extend isAsrs = ResourceId has 'microsoft.signalrservice/signalr', isAwps = ResourceId has 'microsoft.signalrservice/webpubsub',
isFree = SKU == 'Free', isStandard = SKU == 'Standard', isPremium = SKU == 'Premium'
| join kind = inner (MaxConnectionCount_Daily | where Date >= ago(60d) | summarize count() by Date, SubscriptionId) on Date, SubscriptionId
| join kind = leftouter SubscriptionMappings on SubscriptionId
| extend UsageType = iif(CustomerType == 'Internal', CustomerType, BillingType)
| summarize isAsrs = max(isAsrs), isAwps = max(isAwps), isFree = max(isFree), isStandard = max(isStandard), isPremium = max(isPremium) by Date, SubscriptionId, SegmentName, UsageType;
raw
| where isStandard or isFree or isPremium
| summarize OrJoin = dcount(SubscriptionId, 4), AndJoin = dcountif(SubscriptionId, isAwps and isAsrs, 4), 
  Asrs = dcountif(SubscriptionId, isAsrs, 4), Awps = dcountif(SubscriptionId, isAwps, 4) by Date, SKU = ' JOIN(OR)', SegmentName, UsageType
| extend Temp = pack(' JOIN(OR)', OrJoin, ' JOIN(AND)', AndJoin, 'SignalR', Asrs, 'WebPubSub', Awps)
| mv-expand kind = array Temp
| project Date, SKU, UsageType, SegmentName, Service = tostring(Temp[0]), SubscriptionCnt = toint(Temp[1])
```

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
