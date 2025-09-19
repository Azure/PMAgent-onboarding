# SignalR and Web PubSub - Product and Data Overview Template

## 1. Product Overview

> Draft: SignalR and Web PubSub provide real-time messaging services enabling bidirectional communication between clients and servers. This onboarding adds schema context and Kusto query playbooks focused on OKRs (ARR and AI customer growth), usage (revenue, connections, messages), service-type growth (SignalR/Web PubSub/SocketIO), feature tracking (replicas, auto-scale, blazor-server, etc.), external/billable cohorts, and top customer analytics. Lower-priority scopes include Visual Studio integration, QoS analysis, and runtime requests.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**:
> SignalR and Web PubSub
- **Product Nick Names**: 
> [TODO]Data_Engineer: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations.
- **Kusto Cluster**:
> signalrinsights.eastus2
- **Kusto Database**:
> SignalRBI
- **Access Control**:
> [TODO] Data Engineer: If this product’s data has high confidentiality concerns, please specify the allowed groups/users here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

# SignalR and Web PubSub — Kusto Query Playbook

## Overview
Product: SignalR and Web PubSub

Summary: Power BI M query blocks targeting Azure Data Explorer clusters (signalrinsights.eastus2/SignalRBI as main, plus ARMProd and DDTelInsights) covering: OKR analysis, ARR and AI customer growth; usage analysis (revenue, connection count, message count); growth by service type (SignalR/WebPubSub/SocketIO); feature tracking (replicas, auto-scale, blazor-server, etc.); external/billable customers; top customers. Lower priority scenarios include VS integration, QoS analysis, and runtime requests.

Cluster and database:
- Cluster: signalrinsights.eastus2
- Database: SignalRBI
- Alternates used by specific scenarios: armprodgbl.eastus (ARM logs via Unionizer/Requests/HttpIncomingRequests), ddtelinsights (WebTools_Raw)

High-priority focus areas:
- OKR analysis, ARR and AI customer growth
- Usage analysis: revenue, connection count, message count
- Service type growth: SignalR, Web PubSub, Web PubSub for SocketIO
- Feature tracking: replicas, auto-scale, blazor-server, etc.
- External/billable customers
- Top customers

Lower-priority areas:
- Visual Studio integration
- QoS analysis
- RuntimeRequests

## Conventions & Assumptions

### Time semantics
Observed time columns:
- Date (primary in most fact tables)
- env_time (QoS tables: OperationQoS_Daily, ConnectivityQoS_Daily)
- TIMESTAMP (ARM logs via Unionizer/Requests/HttpIncomingRequests)
- AdvancedServerTimestampUtc (developer telemetry in WebTools_Raw)
- TimeStamp (capitalized in some snapshots/goals data)

Canonical Time Column: Date

Standard aliasing patterns:
- QoS → project-rename Date = env_time
- ARM logs → project-rename Date = startofday(TIMESTAMP)
- Developer telemetry → project-rename Date = startofday(AdvancedServerTimestampUtc)
- Snapshots with TimeStamp → project-rename Date = TimeStamp

Typical windows and rollups:
- Recent windows: ago(30d), ago(60d)
- Weekly rollups: Week = startofweek(Date)
- Monthly rollups: Month = startofmonth(Date)
- Day boundary: startofday()
- Some weekly summaries use Week = startofday(endofweek(Date)); prefer normalizing to startofweek(Date)

Timezone:
- Not specified. Assume UTC by default. Be cautious when including “today” as ingestion might lag.

### Freshness & Completeness Gates
- Cross-region day completeness: often gated by Australia East and West Europe.
  - EndDate is computed as the most recent day where both regions report data.
- Current period avoidance:
  - Weekly: Date < startofweek(now())
  - Monthly: Date < startofmonth(now())
- 28-day rolling window is used to build month-like cohorts and avoid partial current month.
- If exact freshness is unknown, prefer using the last fully completed week/month.

Multi-slice completeness gate template:
- Example pattern is used multiple times to gate by EU and Non-EU:
  - Find latest Date for australiaeast and westeurope, pick the earlier of the two as Current.
  - Limit the analysis window to <= Current.
- For stricter gating, require ≥N sentinel regions/shards to report for a day/week before considering it complete.

### Joins & Alignment
Frequent keys:
- ResourceId (case-insensitive usage; normalized with tolower())
- SubscriptionId (parsed from ResourceId or present on facts)
- CloudCustomerGuid (customer entity)
- Region
- SKU, BillingType, CustomerType, SegmentName (from SubscriptionMappings)
- Kind (WebPubSub/SocketIO) and ServiceMode/Extras (from RPSettingLatest)

Join kinds:
- inner: to enforce co-presence/activeness (e.g., gate with MaxConnectionCount_Daily or ensure presence in a window)
- leftouter: to enrich with SubscriptionMappings/RPSettingLatest attributes
- fullouter: when merging with goal datatables to keep all dates

Post-join hygiene:
- Normalize ResourceId case pre-join: extend Role = tolower(ResourceId)
- Resolve duplicates and rename aligned time: project-rename / project-away duplicate IDs (SubscriptionId1, SubscriptionId2, …)
- Use coalesce() where needed to pick non-empty columns

### Filters & Idioms
Common predicates:
- Exclude internal team subscriptions: SubscriptionId !in (SignalRTeamInternalSubscriptionIds) or SignalRTeamInternalSubscriptionIds()
- Exclude non-billable SKUs in revenue/consumption contexts: SKU !in ('MessageCount', 'MessageCountPremium')
- Service detection:
  - IsSignalR = ResourceId has 'microsoft.signalrservice/signalr'
  - IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub'
- AI cohort keywords:
  - ResourceId has 'gpt' or 'ai' or 'ml' or 'cognitive' or contains 'openai' or 'chatgpt'
- Manage RP QoS API filters:
  - Exclude ‘UNCATEGORY’, ‘Internal-ACIS’, ‘INVALID’, and control-list calls like 'GetResource', 'OperationList', etc.
- Case handling: tolower() ResourceId when joining across sources that may differ in case. Prefer has for term match and contains for substring sensitivity where necessary.

Cohorts:
- Construct allowlists/denylists first (e.g., list of APIs, subscriptions) then inner join to enforce.

### Cross-cluster/DB & Sharding
- Same-schema EU sharded tables:
  - union FeatureTrackV2_Daily with FeatureTrackV2_EU_Daily
  - union RuntimeRequestsGroups_Daily with RuntimeRequestsGroups_EU_Daily
  - union RuntimeTransport_Daily with RuntimeTransport_EU_Daily
- ARM logs (Requests/HttpIncomingRequests) reside in armprodgbl.eastus; queries use a function Unionizer('Requests','HttpIncomingRequests')
- Developer telemetry (WebTools_Raw) is in ddtelinsights

Qualification patterns:
- Use union when merging shards, normalize keys and time first, then summarize.
- If calling across clusters/databases directly, use cluster('<name>').database('<db>').<Table> (explicit references are not shown in provided queries but may be needed).

### Table classes
- Fact (events/daily):
  - BillingUsage_Daily, ResourceMetrics, OperationQoS_Daily, ConnectivityQoS_Daily, FeatureTrack*_Daily, Runtime* Daily, ManageRPQosDaily, ConnectionMode_Daily, ManageResourceTags
- Snapshot/Pre-aggregated:
  - Cached_*_Snapshot (many: OKR, EstRevenue, Subs totals, customer/resource flows, top customers)
  - Retention snapshots: SubscriptionRetentionSnapshot, CustomerRetentionSnapshot, ResourceRetentionSnapshot, and AWPS equivalents
  - KPI tables: KPIv2019, KPI_AWPS, KPI_SocketIO
- Functions-like datasets:
  - ResourceFlow_Weekly/Monthly, SubscriptionFlow_Weekly/Monthly, CustomerFlow_Monthly/Weekly (invoked as functions with parameters)

Use facts when you need raw, current-level metrics and guard with completeness. Use snapshots when you need stable, historized, and pre-joined metrics for dashboards.

## Entity & Counting Rules (Core Definitions)
Entity model and keys:
- Resource (ResourceId; normalize tolower())
  - PrimaryResource for replicas: substring(ResourceId, 0, indexof(ResourceId, '/replicas/'))
- Subscription (SubscriptionId; parsed from ResourceId or provided)
- Customer (CloudCustomerGuid; attributes from CustomerModel/SubscriptionMappings)
- Dimensions: Region, SKU, BillingType, CustomerType, SegmentName, Kind (WebPubSub vs SocketIO), ServiceMode

Counting rules:
- Distinct counts use dcount(column, precision), often precision 3–4 for stable aggregations:
  - ResourceCnt = dcount(ResourceId, 3)
  - SubscriptionCnt = dcount(SubscriptionId, 4)
  - CustomerCnt = dcount(CloudCustomerGuid, 3)
- HasConnection definition:
  - MaxConnectionCount > 0 (after joining ResourceMetrics)
- LiveRatio categorization (usage days in period):
  - Weekly example: ActiveDays < 3 → 'Swift', else 'Occasional'
  - Monthly example: ActiveDays < 3 → 'Swift', < 10 → 'Occasional', else 'Dedicate'
- Revenue calculation (usage→cost mapping):
  - Revenue = case(SKU=='Free', 0.0, SKU=='Standard', <StandardUnitPrice>, SKU=='Premium', <PremiumUnitPrice>, 1.0) * Quantity
  - Provided queries use 1.61 for Standard and 2.0 for Premium. Use placeholders in reusable snippets.
- Consumption:
  - “Normalization” in some queries multiplies Quantity by 24 for daily-to-hourly normalized consumption estimates.
- Service identification:
  - IsSignalR/IsWebPubSub derived from ResourceId contains/has specific provider path fragments.

Do/Don’t:
- Do gate time ranges to completed periods (avoid current day/week/month).
- Don’t mix pre-aggregated snapshot metrics with raw fact counting in the same result unless explicitly aligned on time and entity definitions.
- Do normalize ResourceId casing before joins and when deriving PrimaryResource/replica logic.

## Canonical Tables
- BillingUsage_Daily (cluster: signalrinsights.eastus2) [Priority: High]
- MaxConnectionCount_Daily (cluster: signalrinsights.eastus2) [Priority: High]
- SubscriptionMappings (cluster: signalrinsights.eastus2) [Priority: High]
- Cached_ZnOKRARR_Snapshot (cluster: signalrinsights.eastus2) [Priority: High]
- Cached_ZnOKREstRevenueWeekly_Snapshot (cluster: signalrinsights.eastus2) [Priority: High]
- Cached_ZnOKREstRevenueMonthly_Snapshot (cluster: signalrinsights.eastus2) [Priority: High]
- Cached_ZnOKRSubs_Snapshot (cluster: signalrinsights.eastus2) [Priority: High]
- OKRv2021 (cluster: signalrinsights.eastus2) [Priority: High]
- Cached_CuOKRConsumption_Snapshot (cluster: signalrinsights.eastus2) [Priority: High]
- Cached_CuOKRConsumptionWeekly_Snapshot (cluster: signalrinsights.eastus2) [Priority: High]
- Cached_CuOKRConsumptionMonthly_Snapshot (cluster: signalrinsights.eastus2) [Priority: High]
- OperationQoS_Daily (cluster: signalrinsights.eastus2) [Priority: Low]
- ConnectivityQoS_Daily (cluster: signalrinsights.eastus2) [Priority: Low]
- ResourceMetrics (cluster: signalrinsights.eastus2) [Priority: High]
- RPSettingLatest (cluster: signalrinsights.eastus2) [Priority: High]
- ManageRPQosDaily (cluster: signalrinsights.eastus2) [Priority: Low]
- RuntimeRequestsGroups_Daily (cluster: signalrinsights.eastus2) [Priority: Low]
- RuntimeRequestsGroups_EU_Daily (cluster: signalrinsights.eastus2) [Priority: Low]
- RuntimeTransport_Daily (cluster: signalrinsights.eastus2) [Priority: Low]
- RuntimeTransport_EU_Daily (cluster: signalrinsights.eastus2) [Priority: Low]
- ConnectionMode_Daily (cluster: signalrinsights.eastus2) [Priority: Normal]
- KPIv2019 (cluster: signalrinsights.eastus2) [Priority: Normal]
- ChurnCustomers_Monthly (cluster: signalrinsights.eastus2) [Priority: Normal]
- ConvertCustomer_Weekly (cluster: signalrinsights.eastus2) [Priority: Normal]
- Cached_TopSubscriptions_Snapshot (cluster: signalrinsights.eastus2) [Priority: High]
- CustomerModel (cluster: signalrinsights.eastus2) [Priority: High]
- RuntimeResourceTags_Daily (cluster: signalrinsights.eastus2) [Priority: High]
- FeatureTrack_Daily (cluster: signalrinsights.eastus2) [Priority: High]
- FeatureTrackV2_Daily (cluster: signalrinsights.eastus2) [Priority: High]
- FeatureTrackV2_EU_Daily (cluster: signalrinsights.eastus2) [Priority: High]
- FeatureTrack_AutoScale_Daily (cluster: signalrinsights.eastus2) [Priority: High]
- DeleteSurvey (cluster: signalrinsights.eastus2) [Priority: Normal]
- DeleteSurveyWebPubSub (cluster: signalrinsights.eastus2) [Priority: Normal]
- SubscriptionRetentionSnapshot (cluster: signalrinsights.eastus2) [Priority: Normal]
- CustomerRetentionSnapshot (cluster: signalrinsights.eastus2) [Priority: Normal]
- ResourceRetentionSnapshot (cluster: signalrinsights.eastus2) [Priority: Normal]
- Cached_ResourceFlow_Snapshot (cluster: signalrinsights.eastus2) [Priority: Normal]
- ResourceFlow_Weekly (cluster: signalrinsights.eastus2) [Priority: Normal]
- ResourceFlow_Monthly (cluster: signalrinsights.eastus2) [Priority: Normal]
- Cached_SubsTotalWeekly_Snapshot (cluster: signalrinsights.eastus2) [Priority: Normal]
- Cached_SubsTotalMonthly_Snapshot (cluster: signalrinsights.eastus2) [Priority: Normal]
- KPI_AWPS (cluster: signalrinsights.eastus2) [Priority: Normal]
- OKRv2021_AWPS (cluster: signalrinsights.eastus2) [Priority: High]
- OKRv2021_SocketIO (cluster: signalrinsights.eastus2) [Priority: High]
- AwpsRuntimeRequestsGroups_Daily (cluster: signalrinsights.eastus2) [Priority: Low]
- AwpsRetention_SubscriptionSnapshot (cluster: signalrinsights.eastus2) [Priority: Normal]
- AwpsRetention_CustomerSnapshot (cluster: signalrinsights.eastus2) [Priority: Normal]
- AwpsRetention_ResourceSnapshot (cluster: signalrinsights.eastus2) [Priority: Normal]
- KPI_SocketIO (cluster: signalrinsights.eastus2) [Priority: Normal]
- FeedbackSurvey (cluster: signalrinsights.eastus2) [Priority: Normal]
- FeedbackSurveyWebPubSub (cluster: signalrinsights.eastus2) [Priority: Normal]
- CustomerFlow_Weekly (cluster: signalrinsights.eastus2) [Priority: Normal]
- CustomerFlow_Monthly (cluster: signalrinsights.eastus2) [Priority: Normal]
- SubscriptionFlow_Weekly (cluster: signalrinsights.eastus2) [Priority: Normal]
- SubscriptionFlow_Monthly (cluster: signalrinsights.eastus2) [Priority: Normal]
- Unionizer (cluster: armprodgbl.eastus) [Priority: Low]
- Requests (cluster: armprodgbl.eastus) [Priority: Low]
- HttpIncomingRequests (cluster: armprodgbl.eastus) [Priority: Low]
- WebTools_Raw (cluster: ddtelinsights) [Priority: Low]

## Views (Reusable Layers)
None provided. Queries commonly inline their reusable patterns (e.g., gating end dates, revenue/consumption calc, cohort filters). Consider extracting these into Kusto functions for consistency if you maintain the ADX database.

## Query Building Blocks

- Time window template (daily, weekly, monthly, with effective end time)
  - Description: Apply a safe, consistent time filter with a completeness gate to avoid partially ingested days.
  - Snippet:
    ```kusto
    // Daily end-date gate based on sentinel regions
    let EndDate =
        toscalar(
            BillingUsage_Daily
            | where Date > ago(10d) and Region in ('australiaeast', 'westeurope')
            | summarize regions = dcount(Region) by Date
            | where regions >= 2
            | top 1 by Date desc
            | project Date
        );
    // Daily window (last 60d up to the safe EndDate)
    BillingUsage_Daily
    | where Date > ago(60d) and Date <= EndDate
    ```

    ```kusto
    // Weekly complete periods
    let WeekStart = startofweek(now());
    <YourTable>
    | where Date >= startofweek(now(), -N) and Date < WeekStart
    | summarize ... by Week = startofweek(Date)
    ```

    ```kusto
    // Monthly complete periods
    let MonthStart = startofmonth(now());
    <YourTable>
    | where Date >= startofmonth(now(), -M) and Date < MonthStart
    | summarize ... by Month = startofmonth(Date)
    ```

- Join template (normalize IDs, enrich with mappings, gate with activity)
  - Description: Normalize keys for joining across tables; add customer dims; gate on activity.
  - Snippet:
    ```kusto
    let PriceStandard = <StandardUnitPrice>;
    let PricePremium  = <PremiumUnitPrice>;
    BillingUsage_Daily
    | where Date >= ago(30d) and SKU !in ('MessageCount','MessageCountPremium')
    | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
    | extend Role = tolower(ResourceId)
    | join kind=inner (
        MaxConnectionCount_Daily
        | where Date >= ago(60d)
        | project Date, Role = tolower(Role)
    ) on Date, $left.Role == $right.Role
    | join kind=leftouter SubscriptionMappings on SubscriptionId
    | extend Revenue = case(SKU=='Free', 0.0, SKU=='Standard', PriceStandard, SKU=='Premium', PricePremium, 1.0) * Quantity
    ```

- De-duplication pattern
  - Description: Choose the latest record per key or pick single record from multiple runs.
  - Snippet:
    ```kusto
    <Table>
    | summarize arg_max(Date, *) by <Key>
    // or use row_number and filter:
    | extend rk = row_number(1, prev(<PartitionKey>) != <PartitionKey>)
    | where rk == 1
    ```

- Important filters
  - Description: Standard exclusions and cohorts.
  - Snippet:
    ```kusto
    // Exclude internal subscriptions
    | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)

    // Exclude non-billable or special SKUs for revenue
    | where SKU !in ('MessageCount','MessageCountPremium')

    // AI cohort (resource-name keywords)
    | where ResourceId has 'gpt' or ResourceId has 'ai' or ResourceId has 'ml'
        or ResourceId has 'cognitive' or ResourceId contains 'openai' or ResourceId contains 'chatgpt'

    // ManageRP QoS API filter
    | where ApiName !in ('UNCATEGORY','Internal-ACIS','INVALID','GetResource','OperationList','OperationResult','UpdateSubscription')
    | where ApiName !contains 'acs' and ApiName !contains 'acis'
    ```

- Important definitions
  - Description: Reusable definitions for service, revenue, activity, live ratio.
  - Snippet:
    ```kusto
    // Service flags
    | extend IsSignalR    = ResourceId has 'microsoft.signalrservice/signalr'
           , IsWebPubSub  = ResourceId has 'microsoft.signalrservice/webpubsub'

    // Revenue with placeholders (replace with governed unit prices)
    let PriceStandard = <StandardUnitPrice>;
    let PricePremium  = <PremiumUnitPrice>;
    | extend Revenue = case(SKU=='Free', 0.0, SKU=='Standard', PriceStandard, SKU=='Premium', PricePremium, 1.0) * Quantity

    // HasConnection (after joining ResourceMetrics)
    | extend HasConnection = MaxConnectionCount > 0

    // LiveRatio categories from ActiveDays
    | extend LiveRatio = case(ActiveDays < 3, 'Swift', ActiveDays < 10, 'Occasional', 'Dedicate')
    ```

- ID parsing/derivation
  - Description: Extract SubscriptionId from ResourceId and normalize replicas.
  - Snippet:
    ```kusto
    // Parse SubscriptionId
    | parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *

    // Alternate split-based extraction
    | extend SubscriptionId = tostring(split(ResourceId, '/')[2])

    // Normalize primary resource for replicas
    | extend IsReplica = ResourceId has '/replicas/'
    | extend PrimaryResource = iif(IsReplica, substring(ResourceId, 0, indexof(ResourceId, '/replicas/')), ResourceId)
    ```

- Sharded union (EU/Non-EU)
  - Description: Merge same-schema regional shards and normalize time/keys before aggregation.
  - Snippet:
    ```kusto
    let FT =
        union isfuzzy=true
            FeatureTrackV2_Daily,
            FeatureTrackV2_EU_Daily
        | extend Date = startofday(Date)  // normalize day
        | project-away Properties         // drop large fields if not needed
        | extend ResourceId = tolower(ResourceId);
    FT
    | summarize RequestCount = sum(RequestCount) by Date, Feature, ResourceId
    ```

## Example Queries (with explanations)

1) Revenue split by service and segment
- Description: Computes revenue per Date/SKU/SubscriptionId, gated by activity (MaxConnectionCount_Daily) and excluding internal/test SKUs, then aggregates to Total vs SignalR vs WebPubSub and explodes into category-value pairs for easy pivoting. Join to SubscriptionMappings enriches with CustomerType and SegmentName.
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

2) Subscription count trajectory with OKR goals (SignalR vs WebPubSub)
- Description: Builds monthly subscription distinct counts over a combined recent rolling window and historical full months, gated by MaxConnection presence. Joins to a goal datatable to attach SubscriptionGoal and per-service goals. Adapt the rolling windows and goal table as needed.
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
| join kind = fullouter (datatable(TimeStamp: datetime, SubscriptionGoal: real, GrowthGoal: real, SignalRGoal: real, SignalRGrowthGoal: real, WebPubSubGoal: real, WebPubSubGrowthGoal: real)[
datetime(2022-02-28), 24558, 0.038400, 23167, 0.037614, 1390, 0.162995,
datetime(2022-03-31), 25655, 0.039000, 24038, 0.037614, 1617, 0.162995,
datetime(2022-04-30), 26823, 0.039600, 24943, 0.037614, 1880, 0.162995,
datetime(2022-05-31), 28067, 0.040200, 25881, 0.037614, 2186, 0.162995,
datetime(2022-06-30), 29397, 0.041000, 26854, 0.037614, 2543, 0.162995,
datetime(2022-07-31), 30822, 0.041700, 27864, 0.037614, 2957, 0.162995,
datetime(2022-08-31), 32352, 0.042600, 28912, 0.037614, 3439, 0.162995,
datetime(2022-09-30), 34000, 0.043500, 30000, 0.037614, 4000, 0.162995]) on TimeStamp
| extend TimeStamp = iif(isempty(TimeStamp), TimeStamp1, TimeStamp)
| project-away TimeStamp1
```

3) Consumption split by service and segment
- Description: Similar to revenue but aggregates a normalized consumption metric (Quantity * 24). Gated by activity and enriched with SubscriptionMappings.
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

4) AI cohort 28-day rolling vs goals
- Description: Defines a 28-day rolling cohort using AI-related keywords and compares the latest two periods with historical monthly ends. Joins with monthly growth goals.
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

5) QoS rolling windows (SignalR)
- Description: Calculates rolling 7-day and 28-day QoS by re-aligning to the latest env_time (QoS data time) and recomputing uptime ratio over the respective windows. Adapt to ConnectivityQoS_Daily similarly.
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

6) Daily resource totals with completeness gate (SignalR)
- Description: Uses a cross-region EndDate gate to avoid partial last day, then computes resource counts by SKU/Region and flags HasConnection via ResourceMetrics. Useful for daily active footprint.
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

7) Top subscriptions: time-series metrics across usage and activity (SignalR)
- Description: For a curated list of top subscriptions, joins daily ResourceMetrics to BillingUsage_Daily and emits a category-value series (PaidUnits, Revenue, Messages, Connections, Resources). Handy to chart multiple KPIs stacked.
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

8) Feature tracking (SignalR) across shards, gated by SKU presence
- Description: Unions EU and non-EU feature tracking, normalizes time, enriches by SKU presence from BillingUsage_Daily (excluding message-only SKUs), and summarizes weekly request counts by feature.
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

9) Customer/subscription/resource totals per day by customer type (SignalR)
- Description: Combines ResourceMetrics and BillingUsage_Daily to ensure broad coverage, excludes internal, enriches with SubscriptionMappings, and emits distinct entity counts by Date/CustomerType.
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

## Reasoning Notes (only if uncertain)
- Timezone: Not specified for data; assume UTC across all calculations to avoid confusion. This impacts “today” inclusions; conservative stance avoids current day/week/month.
- Unit prices: Queries show 1.61 (Standard) and 2.0 (Premium). For reusable templates, treat these as governed inputs (<StandardUnitPrice>/<PremiumUnitPrice>) to avoid hardcoding.
- Weekly time label: Some queries use startofday(endofweek(Date)) while others use startofweek(Date). We adopt startofweek(Date) as canonical to reduce confusion; ensure consistent use when joining.
- EU/non-EU gating: Sentinel regions australiaeast and westeurope are used for completeness. Alternate sentinel sets could be considered if coverage shifts regionally.
- dcount precision: Provided queries use 3–4 for distinct counts; we adopt precision 3 for resources/customers, 4 for subscriptions to stabilize UI aggregates. This can be tuned based on accuracy vs performance needs.
- Sharded unions: We assume FeatureTrackV2* and Runtime* EU tables share schema with non-EU. If schema diverges, normalize columns before union.
- HasConnection: Interpreted as MaxConnectionCount > 0 post-join with ResourceMetrics. If MaxConnectionCount is missing (no join), treat as false.
- AI cohort keywords: Present as simple text filters; may yield false positives/negatives. Consider centralizing cohort lists for consistency and updates.
- Developer telemetry cluster (ddtelinsights): Only used for VS/WebTools insights; lower priority but ensure AdvancedServerTimestampUtc is used consistently for time alignment.