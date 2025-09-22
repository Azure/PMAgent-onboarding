# SignalR and Web PubSub - Product and Data Overview Template

## 1. Product Overview

SignalR and Web PubSub provide real-time messaging services enabling persistent connections, pub/sub messaging, and serverless integration. This onboard schema supports Power BI report blocks powered by Azure Data Explorer (Kusto) for OKR analysis (ARR, consumption), usage analytics (revenue, connections, messages), subscription/customer/resource totals and flows, feature tracking, top customers, QoS, management API QoS, Visual Studio integration telemetry, and related labels/snapshots.

## 2. Data Platform Overview

- Data Storage: Azure Data Explorer (ADX)
- Product: SignalR and Web PubSub
- Product Nick Names:
  - [TODO]Data_Engineer: Provide common nicknames/abbreviations (e.g., SignalR, ASRS, Web PubSub, AWPS, SRR, WPS, etc.). These help PMAgent map user phrasing to the correct product.
- Kusto Cluster: signalrinsights.eastus2
- Kusto Database: SignalRBI
- Access Control:
  - [TODO] Data Engineer: If this product’s data requires restricted access, list the approved security groups/users. If blank, general users may run analyses, including cross-product scenarios.

-----

Kusto Query Playbook

Tables:
- BillingUsage_Daily (Cluster: signalrinsights.eastus2, Priority: High)
- MaxConnectionCount_Daily (Cluster: signalrinsights.eastus2, Priority: High)
- SubscriptionMappings (Cluster: signalrinsights.eastus2, Priority: High)
- ResourceMetrics (Cluster: signalrinsights.eastus2, Priority: High)
- RPSettingLatest (Cluster: signalrinsights.eastus2, Priority: High)
- OperationQoS_Daily (Cluster: signalrinsights.eastus2, Priority: Low)
- FeatureTrackV2_Daily (Cluster: signalrinsights.eastus2, Priority: High)
- FeatureTrackV2_EU_Daily (Cluster: signalrinsights.eastus2, Priority: High)
- Cached_TopSubscriptions_Snapshot (Cluster: signalrinsights.eastus2, Priority: High)
- ConnectionMode_Daily (Cluster: signalrinsights.eastus2, Priority: Normal)
- ManageRPQosDaily (Cluster: signalrinsights.eastus2, Priority: Normal)
- RuntimeRequestsGroups_Daily (Cluster: signalrinsights.eastus2, Priority: Low)
- RuntimeRequestsGroups_EU_Daily (Cluster: signalrinsights.eastus2, Priority: Low)

Views:

- View Name: ActiveBilling
  Description: Align BillingUsage_Daily with activity (MaxConnectionCount_Daily) and enrich with SubscriptionMappings for consistent cohorting across daily usage.
  Tables Used: BillingUsage_Daily, MaxConnectionCount_Daily, SubscriptionMappings
  Views Used: 
  Query:
  ```kusto
  let ActiveBilling = (startTime: datetime=ago(60d), endTime: datetime=now()) {
    BillingUsage_Daily
    | where Date >= startTime and Date < endTime
    | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
    | join kind=inner (
        MaxConnectionCount_Daily
        | where Date >= startTime - 30d and Date < endTime
        | summarize count() by Date, SubscriptionId
      ) on Date, SubscriptionId
    | join kind=leftouter SubscriptionMappings on SubscriptionId
    | extend UsageType = iif(CustomerType == 'Internal', CustomerType, BillingType)
  };
  ActiveBilling();
  ```

- View Name: LatestCompleteDay
  Description: Compute the latest complete day using a multi-region completeness gate to avoid partial data periods.
  Tables Used: BillingUsage_Daily
  Views Used:
  Query:
  ```kusto
  let LatestCompleteDay = () {
    toscalar(
      BillingUsage_Daily
      | where Date > ago(10d) and Region in ('australiaeast', 'westeurope')
      | summarize Regions = dcount(Region) by Date
      | where Regions >= 2
      | top 1 by Date desc
      | project Date
    )
  };
  print EndDate = LatestCompleteDay();
  ```

- View Name: ResourceMetricsCanonical
  Description: Canonicalize ResourceId, strip replicas, and enrich ResourceMetrics with RP settings and SubscriptionMappings for downstream analysis by service label.
  Tables Used: ResourceMetrics, RPSettingLatest, SubscriptionMappings
  Views Used:
  Query:
  ```kusto
  let ResourceMetricsCanonical = (serviceLabel:string) {
    ResourceMetrics
    | where ResourceId has serviceLabel
    | parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
    | extend ResourceId = tolower(iif(ResourceId has '/replicas/',
                     substring(ResourceId, 0, indexof(ResourceId, '/replicas/')), ResourceId))
    | join kind=leftouter (RPSettingLatest | extend ResourceId = tolower(ResourceId)) on ResourceId
    | join kind=inner SubscriptionMappings on SubscriptionId
  };
  ResourceMetricsCanonical('microsoft.signalrservice/signalr');
  ```

Reusable Queries and Snippets:

```kusto
let ActiveBilling = (startTime: datetime=ago(60d), endTime: datetime=now()) {
  BillingUsage_Daily
  | where Date >= startTime and Date < endTime
  | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
  | join kind=inner (
      MaxConnectionCount_Daily
      | where Date >= startTime - 30d and Date < endTime
      | summarize count() by Date, SubscriptionId
    ) on Date, SubscriptionId
  | join kind=leftouter SubscriptionMappings on SubscriptionId
  | extend UsageType = iif(CustomerType == 'Internal', CustomerType, BillingType)
};
ActiveBilling();
```

```kusto
let LatestCompleteDay = () {
  toscalar(
    BillingUsage_Daily
    | where Date > ago(10d) and Region in ('australiaeast', 'westeurope')
    | summarize Regions = dcount(Region) by Date
    | where Regions >= 2
    | top 1 by Date desc
    | project Date
  )
};
print EndDate = LatestCompleteDay();
```

```kusto
let ResourceMetricsCanonical = (serviceLabel:string) {
  ResourceMetrics
  | where ResourceId has serviceLabel
  | parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
  | extend ResourceId = tolower(iif(ResourceId has '/replicas/',
                   substring(ResourceId, 0, indexof(ResourceId, '/replicas/')), ResourceId))
  | join kind=leftouter (RPSettingLatest | extend ResourceId = tolower(ResourceId)) on ResourceId
  | join kind=inner SubscriptionMappings on SubscriptionId
};
ResourceMetricsCanonical('microsoft.signalrservice/signalr');
```

```kusto
let lookbackDays = 60d;
let startDate = ago(lookbackDays);
let endDate = now();
let EndDate = toscalar(
  BillingUsage_Daily
  | where Date > ago(10d) and Region in ('australiaeast', 'westeurope')
  | summarize Regions = dcount(Region) by Date
  | where Regions >= 2
  | top 1 by Date desc
  | project Date
);
BillingUsage_Daily
| where Date >= startDate and Date <= EndDate
```

```kusto
BillingUsage_Daily
| extend ResourceIdLower = tolower(ResourceId)
| join kind=inner (
    MaxConnectionCount_Daily
    | extend ResourceIdLower = tolower(Role)  // Role holds ResourceId in this table
    | project Date, ResourceIdLower
  ) on Date, ResourceIdLower
| join kind=leftouter SubscriptionMappings on SubscriptionId
| project-away ResourceIdLower
```

```kusto
T
| summarize any(*) by Week=startofweek(Date), ResourceId
```

```kusto
T | summarize arg_max(Date, *) by ResourceId
```

```kusto
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| extend IsSignalR = ResourceId has 'microsoft.signalrservice/signalr',
         IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub'
| where SKU in ('Free','Standard','Premium')
| where SKU !in ('MessageCount','MessageCountPremium')
```

```kusto
| extend UnitPrice =
    case(SKU == 'Free', 0.0,
         SKU == 'Standard', <UnitPriceStandard>,
         SKU == 'Premium', <UnitPricePremium>,
         <UnitPriceDefault>)
| extend Revenue = UnitPrice * Quantity
| extend UsageType = iif(CustomerType == 'Internal', 'Internal', BillingType)
```

```kusto
| parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
| extend ResourceId = tolower(ResourceId),
         PrimaryResource = iif(ResourceId has '/replicas/',
           substring(ResourceId, 0, indexof(ResourceId, '/replicas/')), ResourceId)
```

```kusto
let RuntimeRequests =
  RuntimeRequestsGroups_Daily
  | where Date > ago(60d) and Category != 'Transport'
| union
  (RuntimeRequestsGroups_EU_Daily
   | where Date > ago(60d) and Category != 'Transport');
RuntimeRequests
| summarize ResourceCount = dcount(ResourceId), RequestCount = sum(RequestCount) by Date, Category, Metrics
```

```kusto
let raw = BillingUsage_Daily
| where Date >= ago(30d) and SKU !in ('MessageCount', 'MessageCountPremium')
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| extend Role = tolower(ResourceId)
| join kind=inner (
    MaxConnectionCount_Daily
    | where Date >= ago(60d)
    | project Date, Role = tolower(Role)
  ) on Date, $left.Role == $right.Role
| extend isAsrs = ResourceId has 'microsoft.signalrservice/signalr',
         isAwps = ResourceId has 'microsoft.signalrservice/webpubsub',
         Income = case(SKU == 'Free', 0.0,
                       SKU == 'Standard', <UnitPriceStandard>,
                       SKU == 'Premium', <UnitPricePremium>,
                       <UnitPriceDefault>) * Quantity
| summarize Income = sum(Income) by Date, SKU, SubscriptionId, isAsrs, isAwps
| join kind=leftouter SubscriptionMappings on SubscriptionId;
raw
| summarize Total = sum(Income),
            Asrs = sumif(Income, isAsrs),
            Awps = sumif(Income, isAwps) by Date, SKU, CustomerType, SegmentName
```

```kusto
let raw = BillingUsage_Daily
| where Date >= ago(30d) and SKU !in ('MessageCount','MessageCountPremium')
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| extend Role = tolower(ResourceId)
| join kind=inner (
    MaxConnectionCount_Daily
    | where Date >= ago(60d)
    | project Date, Role = tolower(Role)
  ) on Date, $left.Role == $right.Role
| extend isAsrs = ResourceId has 'microsoft.signalrservice/signalr',
         isAwps = ResourceId has 'microsoft.signalrservice/webpubsub'
| summarize Consumption = sum(Quantity) * 24 by Date, SKU, SubscriptionId, isAsrs, isAwps
| join kind=leftouter SubscriptionMappings on SubscriptionId;
raw
| summarize Total = sum(Consumption),
            Asrs = sumif(Consumption, isAsrs),
            Awps = sumif(Consumption, isAwps) by Date, SKU, CustomerType, SegmentName
```

```kusto
let NonEU = BillingUsage_Daily | where Region == 'australiaeast' | top 1 by Date desc | project Date;
let EU = BillingUsage_Daily | where Region == 'westeurope' | top 1 by Date desc | project Date;
let Current = toscalar(NonEU | union EU | top 1 by Date asc);
let DoM = 28d;
let LatestPeriod = BillingUsage_Daily
| where Date > Current - DoM and Date <= Current
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| where ResourceId has 'gpt' or ResourceId has 'ai' or ResourceId has 'ml' or
       ResourceId has 'cognitive' or ResourceId contains 'openai' or ResourceId contains 'chatgpt'
| extend IsSignalR = ResourceId has 'microsoft.signalrservice/signalr',
         IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub',
         Month = startofday(Current)
| summarize SubscriptionCnt = dcount(SubscriptionId),
            SignalR = dcountif(SubscriptionId, IsSignalR, 4),
            WebPubSub = dcountif(SubscriptionId, IsWebPubSub, 4) by Month;
let LatestPeriodBeforeLast = BillingUsage_Daily
| where Date > Current - 2*DoM and Date <= Current - DoM
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| where ResourceId has 'gpt' or ResourceId has 'ai' or ResourceId has 'ml' or
       ResourceId has 'cognitive' or ResourceId contains 'openai' or ResourceId contains 'chatgpt'
| extend IsSignalR = ResourceId has 'microsoft.signalrservice/signalr',
         IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub',
         Month = startofday(Current) - 1h
| summarize SubscriptionCnt = dcount(SubscriptionId),
            SignalR = dcountif(SubscriptionId, IsSignalR, 4),
            WebPubSub = dcountif(SubscriptionId, IsWebPubSub, 4) by Month;
let Historical = BillingUsage_Daily
| where Date >= endofmonth(now(), -14) and Date < startofmonth(Current)
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| where ResourceId has 'gpt' or ResourceId has 'ai' or ResourceId has 'ml' or
       ResourceId has 'cognitive' or ResourceId contains 'openai' or ResourceId contains 'chatgpt'
| extend IsSignalR = ResourceId has 'microsoft.signalrservice/signalr',
         IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub',
         Month = startofday(endofmonth(Date))
| summarize SubscriptionCnt = dcount(SubscriptionId),
            SignalR = dcountif(SubscriptionId, IsSignalR, 4),
            WebPubSub = dcountif(SubscriptionId, IsWebPubSub, 4) by Month;
LatestPeriod
| union LatestPeriodBeforeLast
| union Historical
| join kind=fullouter (
  datatable(Month: datetime, SubscriptionGoal: int, SubscriptionGrowthGoal: real) [
    datetime(2025-06-30), 395, 0.08,
    datetime(2025-07-31), 426, 0.08,
    datetime(2025-08-31), 460, 0.08,
    datetime(2025-09-30), 496, 0.08,
    datetime(2025-10-31), 535, 0.08,
    datetime(2025-11-30), 577, 0.08,
    datetime(2025-12-31), 623, 0.08
  ]) on Month
| extend Month = iif(isempty(Month), Month1, Month)
| project-away Month1
```

```kusto
let raw = OperationQoS_Daily
| where env_time > ago(43d) and resourceId has '/signalr/'
| summarize Qos = iif(sum(totalTimeSec) == 0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec)),
          UpTime = sum(totalUpTimeSec), TotalTime = sum(totalTimeSec)
  by Date = env_time, Region = env_cloud_location, ResourceId = env_cloud_role;
raw
| summarize TotalOperation = sum(TotalTime),
            Qos = iif(sum(TotalTime) == 0, 1.0, 1.0*sum(UpTime)/sum(TotalTime)),
            SlaAttainment = 1.0 * dcountif(ResourceId, Qos >= 0.999, 4) / dcount(ResourceId, 4)
  by Date, Region
| union (
  raw
  | summarize TotalOperation = sum(TotalTime),
              Qos = iif(sum(TotalTime) == 0, 1.0, 1.0*sum(UpTime)/sum(TotalTime)),
              SlaAttainment = 1.0 * dcountif(ResourceId, Qos >= 0.999, 4) / dcount(ResourceId, 4)
    by Date, Region = 'Overall')
```

```kusto
let EndDate = toscalar(BillingUsage_Daily
  | where Date > ago(10d) and Region in ('australiaeast','westeurope')
  | summarize counter = dcount(Region) by Date
  | where counter >= 2
  | top 1 by Date desc
  | project Date);
BillingUsage_Daily
| where Date > ago(61d) and Date <= EndDate and ResourceId has 'microsoft.signalrservice/signalr'
| extend SubscriptionId = tostring(split(ResourceId, '/')[2])
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
| summarize SKU = max(SKU), Region = max(Region) by Date, ResourceId
| join kind=leftouter ResourceMetrics on Date, ResourceId
| extend HasConnection = iif(isempty(ResourceId1), false, MaxConnectionCount > 0)
| summarize Total = dcount(ResourceId) by Date, SKU, Region, HasConnection
```

```kusto
FeatureTrackV2_Daily
| union FeatureTrackV2_EU_Daily
| where Date > startofweek(now()) - 56d
| project-away Properties
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

```kusto
let label = 'microsoft.signalrservice/signalr';
Cached_TopSubscriptions_Snapshot
| where Service == 'SignalR'
| project SubscriptionId
| join kind=inner (
    ResourceMetrics
    | where Date > startofday(now(), -29) and ResourceId has label
    | parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
    | summarize MaxConnectionCount = sum(MaxConnectionCount),
                MessageCount = sum(SumMessageCount) by Date, SubscriptionId
  ) on SubscriptionId
| join kind=inner (
    BillingUsage_Daily
    | where Date > startofday(now(), -29) and ResourceId has label
    | extend Revenue = case(SKU=='Standard', <UnitPriceStandard>,
                            SKU=='Premium', <UnitPricePremium>,
                            SKU=='Free', 0.0, <UnitPriceDefault>) * Quantity
    | summarize Revenue = sum(Revenue),
                PaidUnits = sumif(Quantity, SKU in ('Standard','Premium')),
                ResourceCount = dcount(ResourceId) by Date, SubscriptionId
  ) on SubscriptionId, Date
| extend Temp = pack('PaidUnits', PaidUnits, 'Revenue', Revenue, 'Messages', MessageCount,
                     'Connections', MaxConnectionCount, 'Resources', ResourceCount)
| mv-expand kind=array Temp
| project Date, SubscriptionId, Category = tostring(Temp[0]), Value = toreal(Temp[1])
```

```kusto
BillingUsage_Daily
| where Date >= startofweek(now(), -8)
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
| where ResourceId has 'microsoft.signalrservice/signalr'
| join kind=inner ResourceMetrics on ResourceId, Date
| summarize Conn = max(MaxConnectionCount),
            SKU = max(SKU), Region = max(Region), ActiveDays = dcount(Date)
  by Week = startofweek(Date), ResourceId
| project Week, ResourceId, Category = 'Total', Region, SKU,
         HasConnection = Conn > 0,
         LiveRatio = case(ActiveDays < 3, 'Swift', 'Occasional')
| summarize ResourceCnt = dcount(ResourceId, 3)
  by Week, Category, Region, SKU, HasConnection, LiveRatio
```

```kusto
ConnectionMode_Daily
| where Date > ago(60d) and ResourceId has 'microsoft.signalrservice/signalr'
| summarize ResourceCount = dcount(ResourceId),
            ConnectionCount = sum(ServerlessConnection) + sum(ProxyConnection)
  by Date, ServiceMode
```

```kusto
let dateFilter = ManageRPQosDaily
| top 1 by Date desc
| project Date, fakeKey = 1;
ManageRPQosDaily
| where Date > ago(10d)
| extend fakeKey = 1
| join kind=inner dateFilter on fakeKey
| where Date > Date1 - 7d and ApiName !in ('UNCATEGORY')
| summarize Qos = 1.0*sumif(Count, Result in ('Success','Timeout','CustomerError'))/sum(Count)
  by Date = Date1, Type = 'Rolling7'
| union (
  ManageRPQosDaily
  | where Date > ago(30d)
  | extend fakeKey = 1
  | join kind=inner dateFilter on fakeKey
  | where Date > Date1 - 28d and ApiName !in ('UNCATEGORY')
  | summarize Qos = 1.0*sumif(Count, Result in ('Success','Timeout','CustomerError'))/sum(Count)
    by Date = Date1, Type = 'Rolling28'
)
```