# SignalR and Web PubSub - Product and Data Overview Template

## 1. Product Overview

SignalR and Web PubSub combine real-time messaging services (Azure SignalR Service) and event-driven WebSocket-based services (Azure Web PubSub, including Socket.IO). This draft schema/playbook focuses on OKR analysis (ARR and AI customer growth), usage analysis (revenue, connection count, message count), service type growth (SignalR, WebPubSub, Socket.IO), feature tracking (replicas, auto-scale, Blazor Server, Aspire, Socket.IO), external and billable customers, top customers, retention, and customer segmentation. Lower-priority areas include VS integration, QoS analysis, and RuntimeRequests. Main ADX cluster: signalrinsights.eastus2. Main ADX database: SignalRBI. Note: One cross-cluster source appears for VS WebTools telemetry: cluster('ddtelinsights').

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

# SignalR and Web PubSub - Product and Data Overview Template

1. Overview
- SignalR and Web PubSub combine real-time messaging services (Azure SignalR Service) and event-driven WebSocket-based services (Azure Web PubSub, including Socket.IO). The onboarding inputs provide comprehensive Kusto query patterns for OKR analysis (ARR and AI customer growth), usage analysis (revenue, connection count, message count), service type growth (SignalR, WebPubSub, Socket.IO), feature tracking (replicas, auto-scale, Blazor Server, Aspire, Socket.IO), external and billable customers, top customers, retention, and customer segmentation. Lower-priority areas include VS integration, QoS analysis, and RuntimeRequests.
- Main cluster: signalrinsights.eastus2
- Main database: SignalRBI
- Note: One cross-cluster source appears for VS WebTools telemetry: cluster('ddtelinsights').

2. Conventions & Assumptions
- Time semantics
  - Observed timestamp columns:
    - Date (primary canonical time)
    - env_time (QoS tables)
    - AdvancedServerTimestampUtc (VS WebTools)
    - Derived slices: Week = startofweek(Date), Month = startofmonth(Date), TimeStamp (various cached snapshots)
  - Canonical Time Column: Date
    - Alias via: project-rename TimeCol = Date or by deriving Date from env_time/AdvancedServerTimestampUtc:
      - OperationQoS_Daily | project-rename Date = env_time
      - WebTools_Raw | extend Date = startofday(AdvancedServerTimestampUtc)
  - Typical windows and binning:
    - Recent windows: ago(30d), ago(60d)
    - Weekly/monthly slices: startofweek(), startofmonth(), endofmonth()
    - Rolling periods: 7-day and 28-day windows using a last-complete anchor time
    - 28-day cohort windows for AI-related customer growth (DoM = 28d)
  - Timezone: Not explicitly stated. Assume UTC (default in Kusto). Avoid using current-day data without a completeness gate.

- Freshness & Completeness Gates
  - Current day/period is often incomplete. Many queries:
    - Anchor to last available Date via toscalar(Table | top 1 by Date desc)
    - Normalize current/previous month end times, sometimes adjusting by -1h to avoid partials
    - Multi-slice gate pattern: choose the latest Date where ≥2 sentinel regions reported (e.g., australiaeast and westeurope)
  - Recommended effective end time strategy:
    - Weekly/Monthly: use Date < startofweek(now()) or Date < startofmonth(now())
    - Daily: use last day passing region completeness checks
    - For safety, exclude “today” and consider lag for EU shards when unioning EU/non-EU tables

- Joins & Alignment
  - Frequent keys:
    - SubscriptionId, ResourceId, CloudCustomerGuid, Region, SKU
    - Parse SubscriptionId from ResourceId:
      - parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
      - or extend SubscriptionId = tostring(split(ResourceId, '/')[2])
  - Typical joins:
    - Enrichment: leftouter to SubscriptionMappings (adds CustomerType, BillingType, SegmentName, Offer info)
    - Activity gating: inner join with MaxConnectionCount_Daily on Date+SubscriptionId or Date+ResourceId
    - Metrics enrichment: leftouter join to ResourceMetrics on Date+ResourceId
    - Date alignment: compute Week/Month on both sides before join
  - Post-join hygiene:
    - Normalize ResourceId: tolower(ResourceId)
    - Collapse replicas: primary = substring(ResourceId, 0, indexof(ResourceId, '/replicas/'))
    - Resolve duplicate columns via project-away/rename
    - Coalesce aligned times if fullouter joins introduced TimeStamp1/Date1

- Filters & Idioms
  - Default exclusions:
    - Internal subscriptions: SubscriptionId !in (SignalRTeamInternalSubscriptionIds) or SignalRTeamInternalSubscriptionIds()
    - Exclude pre-aggregated SKUs where appropriate: SKU !in ('MessageCount', 'MessageCountPremium')
  - Service detection via ResourceId:
    - SignalR: ResourceId has 'microsoft.signalrservice/signalr'
    - WebPubSub: ResourceId has 'microsoft.signalrservice/webpubsub'
    - Socket.IO: RPSettingLatest Kind == 'SocketIO'
  - AI cohort identification (resource name heuristic):
    - ResourceId has 'gpt' or 'ai' or 'ml' or 'cognitive' or contains 'openai' or 'chatgpt'
  - Text matching:
    - Use has for tokenized/search (fast, token-aware), contains for substring; standardize case with tolower()

- Cross-cluster/DB & Sharding
  - Qualifying sources:
    - cluster('signalrinsights.eastus2').database('SignalRBI').TableName
    - VS WebTools: cluster('ddtelinsights').database('<db>').WebTools_Raw
  - EU/non-EU shards:
    - union EU counterparts (e.g., FeatureTrackV2_Daily ∪ FeatureTrackV2_EU_Daily; RuntimeRequestsGroups_Daily ∪ RuntimeRequestsGroups_EU_Daily)
    - Normalize time and key columns pre-union; then summarize

- Table classes
  - Facts (daily/events):
    - BillingUsage_Daily (billing usage, SKU, Quantity, ResourceId)
    - MaxConnectionCount_Daily (gating presence by Date+Subscription)
    - ResourceMetrics (MaxConnectionCount, SumMessageCount, AvgConnectionCount)
    - QoS: OperationQoS_Daily, ConnectivityQoS_Daily
    - ManageRPQosDaily, ManageResourceTags, RuntimeRequestsGroups_*_Daily, RuntimeTransport_*_Daily, ConnectionMode_Daily, FeatureTrack*_Daily, RuntimeResourceTags_Daily
  - Snapshot/Pre-aggregated:
    - Cached_*_Snapshot (ARR, revenue weekly/monthly, subs, flows, top subscriptions)
    - KPI tables, OKRv2021*, ChurnCustomers_Monthly, ConvertCustomer_Weekly
    - Retention snapshots: SubscriptionRetentionSnapshot, CustomerRetentionSnapshot, ResourceRetentionSnapshot and AWPS variants
  - When to use:
    - Facts for fresh/detailed slicing and joins
    - Snapshots for quicker OKR/KPI/retention/flow reporting (caveat: refresh cadence unknown; confirm staleness)

3. Entity & Counting Rules (Core Definitions)
- Entity model
  - Resource → Subscription → Customer
  - Keys:
    - Resource: ResourceId (normalize tolower; collapse replicas to primary id)
    - Subscription: SubscriptionId
    - Customer: CloudCustomerGuid (via SubscriptionMappings)
  - Standard grouping levels:
    - By Day/Week/Month + service (SignalR/WebPubSub/SocketIO) + SKU + Region + CustomerType/BillingType + SegmentName

- Counting rules and definitions
  - Active resource:
    - HasConnection: max(MaxConnectionCount) > 0 (from ResourceMetrics)
    - LiveRatio (resource activity level):
      - Swift: ActiveDays < 3 (in slice)
      - Occasional: ActiveDays < 10
      - Dedicate: otherwise
  - Subscription/resource/customer counts:
    - Use dcount with reliability parameter (e.g., dcount(key, 3 or 4))
  - Revenue/consumption:
    - Revenue = Quantity × UnitPrice(SKU)
      - Use placeholders: <UnitPriceFree>=0, <UnitPriceStandard>, <UnitPricePremium>
    - Consumption often normalized (×24) or filtered to paid SKUs as needed
  - QoS:
    - Qos = if(sum(totalTimeSec) == 0, 1.0, sum(totalUpTimeSec)/sum(totalTimeSec))
    - SlaAttainment = dcountif(ResourceId, Qos >= <SlaThreshold>)/dcount(ResourceId)
      - SignalR thresholds commonly 0.999 (ops) and 0.995 (connectivity); treat as parameters

4. Views (Reusable Layers)

5. Query Building Blocks (Copy-paste snippets, contains snippets and description)
- Time window template
  - Description: Choose a safe end time and bin to Week/Month to avoid incomplete periods.
  - Query:
    ```kusto
    // Last complete day where both sentinel regions reported (multi-slice gate)
    let EndDate =
        toscalar(
            BillingUsage_Daily
            | where Date > ago(10d) and Region in ('australiaeast', 'westeurope')
            | summarize RegionsReporting = dcount(Region) by Date
            | where RegionsReporting >= 2
            | top 1 by Date desc
            | project Date
        );
    // Weekly/Monthly safe windows
    let StartWeek = startofweek(now(), -8);
    let EndWeek = startofweek(now());     // exclude current week
    let StartMonth = startofmonth(now(), -12);
    let EndMonth = startofmonth(now());   // exclude current month
    ```

- Join template (keys, pre-alignment, enrichment)
  - Description: Standardize IDs/time, gate by activity, enrich to Customer metadata.
  - Query:
    ```kusto
    let t0 = BillingUsage_Daily
        | where Date between (ago(60d) .. EndDate)
        | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
        | extend ResourceId = tolower(ResourceId) // normalize
        | project Date, ResourceId, SubscriptionId, SKU, Quantity, Region;
    let activity = MaxConnectionCount_Daily
        | where Date between (ago(60d) .. EndDate)
        | project Date, SubscriptionId;
    let enriched =
        t0
        | join kind=inner activity on Date, SubscriptionId
        | join kind=leftouter SubscriptionMappings on SubscriptionId
        | project-away SubscriptionId1;
    enriched
    ```

- De-dup pattern (latest state by key)
  - Description: Use arg_max to select latest state per entity (e.g., RPSettingLatest per ResourceId).
  - Query:
    ```kusto
    RPSettingLatest
    | summarize arg_max(TimeGenerated, *) by ResourceId
    ```

- Important filters
  - Description: Default exclusions and SKU filters (avoid MessageCount for revenue/unit analysis).
  - Query:
    ```kusto
    | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
    | where SKU !in ('MessageCount', 'MessageCountPremium')
    | where ResourceId has 'microsoft.signalrservice/signalr' // or '.../webpubsub'
    ```

- Important definitions (Active, LiveRatio, paid vs free)
  - Description: Standardize “active” and activity cohorting.
  - Query:
    ```kusto
    let activeByWeek =
        ResourceMetrics
        | where Date between (StartWeek .. EndWeek)
        | extend Week = startofweek(Date)
        | summarize Conn = max(MaxConnectionCount), ActiveDays = dcount(Date) by Week, ResourceId
        | extend HasConnection = Conn > 0,
                 LiveRatio = case(ActiveDays < 3, 'Swift', ActiveDays < 10, 'Occasional', 'Dedicate');
    ```

- ID parsing/derivation
  - Description: Extract SubscriptionId from ResourceId; collapse replicas to primary.
  - Query:
    ```kusto
    | parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
    | extend ResourceId = tolower(ResourceId),
             PrimaryResourceId = iif(ResourceId has '/replicas/', substring(ResourceId, 0, indexof(ResourceId, '/replicas/')), ResourceId)
    ```

- Revenue/consumption with placeholders
  - Description: Compute revenue or consumption by SKU and service with configurable unit prices.
  - Query:
    ```kusto
    let UnitPrice = (sku:string) {
        case(
            sku == 'Free', 0.0,
            sku == 'Standard', <UnitPriceStandard>,
            sku == 'Premium', <UnitPricePremium>,
            0.0
        )
    };
    BillingUsage_Daily
    | where Date between (ago(30d) .. EndDate)
    | where SKU !in ('MessageCount', 'MessageCountPremium')
    | extend IsSignalR = ResourceId has 'microsoft.signalrservice/signalr',
             IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub',
             Revenue = todouble(Quantity) * UnitPrice(SKU)
    ```

- Sharded union (EU/Non-EU)
  - Description: Merge same-schema EU/non-EU sources, normalize metric names before summarize.
  - Query:
    ```kusto
    let nonTransport =
        RuntimeRequestsGroups_Daily
        | where Date > ago(60d) and Category != 'Transport';
    let nonTransportEU =
        RuntimeRequestsGroups_EU_Daily
        | where Date > ago(60d) and Category != 'Transport';
    union nonTransport, nonTransportEU
    | extend Metrics = iif(Category == 'RestApiScenario' and (Metrics startswith 'v1' and Metrics !contains 'HubProxy'),
                           replace_string(Metrics, 'v1', 'v1-HubProxy'),
                           Metrics)
    | summarize ResourceCount = dcount(ResourceId), RequestCount = sum(RequestCount)
      by Date, Category, Metrics
    ```

6. Example Queries (with explanations)
- Revenue by Service and SKU (paid units only)
  - Description: Computes daily revenue by service (SignalR/WebPubSub), SKU, and customer segments. Excludes internal subscriptions and message-only SKUs. Use EndDate gate to avoid incomplete data. Replace <UnitPriceStandard>/<UnitPricePremium> before running.
  ```kusto
  let EndDate =
      toscalar(
          BillingUsage_Daily
          | where Date > ago(10d) and Region in ('australiaeast', 'westeurope')
          | summarize RegionsReporting = dcount(Region) by Date
          | where RegionsReporting >= 2
          | top 1 by Date desc
          | project Date
      );
  let raw = BillingUsage_Daily
      | where Date between (ago(30d) .. EndDate)
      | where SKU !in ('MessageCount', 'MessageCountPremium')
      | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
      | extend Role = tolower(ResourceId),
               Revenue = case(SKU == 'Free', 0.0,
                              SKU == 'Standard', <UnitPriceStandard>,
                              SKU == 'Premium', <UnitPricePremium>, 0.0) * Quantity,
               IsSignalR = ResourceId has 'microsoft.signalrservice/signalr',
               IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub'
      | summarize Revenue = sum(Revenue) by Date, SKU, SubscriptionId, IsSignalR, IsWebPubSub
      | join kind=leftouter SubscriptionMappings on SubscriptionId;
  raw
  | summarize Total = sum(Revenue),
              SignalR = sumif(Revenue, IsSignalR),
              WebPubSub = sumif(Revenue, IsWebPubSub)
      by Date, SKU, CustomerType, SegmentName
  ```

- AI customer growth (28-day window)
  - Description: Tracks subscriptions using AI-related resources across rolling 28-day windows, split by service. Uses a Current anchor (last available day), two latest 28-day windows, and historical monthly bins. Apply internal exclusion and AI heuristics.
  ```kusto
  let NonEU = BillingUsage_Daily | where Region == 'australiaeast' | top 1 by Date desc | project Date;
  let EU    = BillingUsage_Daily | where Region == 'westeurope'   | top 1 by Date desc | project Date;
  let Current = toscalar(NonEU | union EU | top 1 by Date asc);
  let DoM = 28d;
  let FilterAI = (s:string) { s has 'gpt' or s has 'ai' or s has 'ml' or s has 'cognitive' or s contains 'openai' or s contains 'chatgpt' };
  let slice = (start:datetime, end:datetime, stamp:datetime) {
      BillingUsage_Daily
      | where Date > start and Date <= end
      | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
      | where FilterAI(tostring(ResourceId))
      | extend IsSignalR = ResourceId has 'microsoft.signalrservice/signalr',
               IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub',
               Month = stamp
      | summarize SubscriptionCnt = dcount(SubscriptionId),
                  SignalR = dcountif(SubscriptionId, IsSignalR, 4),
                  WebPubSub = dcountif(SubscriptionId, IsWebPubSub, 4)
        by Month
  };
  slice(Current - DoM, Current, startofday(Current))
  | union slice(Current - 2*DoM, Current - DoM, startofday(Current) - 1h)
  | union (
      BillingUsage_Daily
      | where Date >= endofmonth(now(), -14) and Date < startofmonth(Current)
      | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
      | where FilterAI(tostring(ResourceId))
      | extend IsSignalR = ResourceId has 'microsoft.signalrservice/signalr',
               IsWebPubSub = ResourceId has 'microsoft.signalrservice/webpubsub',
               Month = startofday(endofmonth(Date))
      | summarize SubscriptionCnt = dcount(SubscriptionId),
                  SignalR = dcountif(SubscriptionId, IsSignalR, 4),
                  WebPubSub = dcountif(SubscriptionId, IsWebPubSub, 4)
        by Month
    )
  ```

- QoS rolling windows (SignalR Operations)
  - Description: Computes rolling 7-day and 28-day QoS anchored on the last env_time observed. Useful to trend service-level uptime using OperationQoS_Daily (SignalR).
  ```kusto
  let df = OperationQoS_Daily | top 1 by env_time desc | project env_time, fk=1;
  OperationQoS_Daily
  | where resourceId has 'microsoft.signalrservice/signalr'
  | extend fk = 1
  | join kind=inner df on fk
  | where env_time > env_time1 - 7d
  | summarize Qos = iif(sum(totalTimeSec) == 0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec)) by Date=env_time1, Type='Rolling7'
  | union (
      OperationQoS_Daily
      | where resourceId has 'microsoft.signalrservice/signalr'
      | extend fk = 1
      | join kind=inner df on fk
      | where env_time > env_time1 - 28d
      | summarize Qos = iif(sum(totalTimeSec) == 0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec)) by Date=env_time1, Type='Rolling28'
    )
  ```

- Resource activity classification (SignalR, weekly)
  - Description: For SignalR resources, bins to weeks, joins usage with metrics, derives HasConnection and LiveRatio to classify resources into activity cohorts by Region and SKU.
  ```kusto
  BillingUsage_Daily
  | where Date between (startofweek(now(), -8) .. startofweek(now()))
  | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
  | where ResourceId has 'microsoft.signalrservice/signalr'
  | join kind=inner ResourceMetrics on ResourceId, Date
  | summarize Conn = max(MaxConnectionCount), SKU = max(SKU), Region = max(Region), ActiveDays = dcount(Date) by Week=startofweek(Date), ResourceId
  | extend HasConnection = Conn > 0, LiveRatio = case(ActiveDays < 3, 'Swift', 'Occasional')
  | summarize ResourceCnt = dcount(ResourceId, 3) by Week, Region, SKU, HasConnection, LiveRatio
  ```

- Feature usage joined with consumption (SignalR, EU+Non-EU)
  - Description: Tracks weekly feature usage by combining FeatureTrackV2_Daily and FeatureTrackV2_EU_Daily, normalizing Date and Category, filtered to SignalR resources with non-message SKUs.
  ```kusto
  FeatureTrackV2_Daily
  | union FeatureTrackV2_EU_Daily
  | where Date > startofweek(now()) - 56d
  | project-away Properties
  | extend Date = startofday(Date),
           Category = case(Feature in ('BlazorServerSide', 'Samples'), Feature,
                           Category endswith 'Ping', substring(Category, 8, indexof(Category, 'Ping') - 8), Category)
  | where ResourceId has 'microsoft.signalrservice/signalr'
  | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
  | join kind=inner (BillingUsage_Daily | where SKU !in ('MessageCount', 'MessageCountPremium')) on Date, ResourceId
  | summarize RequestCount = sum(RequestCount), SKU = max(SKU) by Week=startofweek(Date), Feature, ResourceId, SubscriptionId, Category
  ```

- Top subscriptions daily KPIs (SignalR)
  - Description: For top SignalR subscriptions, expands into PaidUnits/Revenue/Messages/Connections/Resources per day, by joining BillingUsage_Daily with ResourceMetrics. Useful for top customer dashboards.
  ```kusto
  let label = 'microsoft.signalrservice/signalr';
  Cached_TopSubscriptions_Snapshot
  | where Service == 'SignalR'
  | project SubscriptionId
  | join kind=inner (
      ResourceMetrics
      | where Date > startofday(now(), -29) and ResourceId has label
      | parse ResourceId with '/subscriptions/' SubscriptionId:string '/resourceGroups/' *
      | summarize MaxConnectionCount = sum(MaxConnectionCount), MessageCount = sum(SumMessageCount) by Date, SubscriptionId
    ) on SubscriptionId
  | join kind=inner (
      BillingUsage_Daily
      | where Date > startofday(now(), -29) and ResourceId has label
      | extend Revenue = case(SKU=='Standard', <UnitPriceStandard>,
                              SKU=='Premium', <UnitPricePremium>,
                              SKU=='Free', 0.0, 0.0) * Quantity
      | summarize Revenue = sum(Revenue),
                  PaidUnits = sumif(Quantity, SKU in ('Standard', 'Premium')),
                  ResourceCount = dcount(ResourceId)
        by Date, SubscriptionId
    ) on SubscriptionId, Date
  | extend pairs = pack('PaidUnits', PaidUnits, 'Revenue', Revenue, 'Messages', MessageCount, 'Connections', MaxConnectionCount, 'Resources', ResourceCount)
  | mv-expand kv = pairs
  | project Date, SubscriptionId, Category = tostring(kv[0]), Value = toreal(kv[1])
  ```

- Weekly subscription/customer totals from cached snapshots (SignalR)
  - Description: Uses pre-aggregated weekly snapshot to count distinct subscriptions or customers by multiple dims (fast for dashboards). Joins to SubscriptionMappings for CustomerType/SegmentName.
  ```kusto
  Cached_SubsTotalWeekly_Snapshot
  | where ServiceType == 'SignalR'
  | join kind=leftouter SubscriptionMappings on SubscriptionId
  | summarize SubscriptionCnt = dcount(SubscriptionId, 3)
      by Week, Region, OfferType, OfferName, BillingType, SKU, CustomerType, HasConnection, LiveRatio
  ```

- Retention by cohort (subscription-level, monthly)
  - Description: Computes retention matrix (Total vs Retain vs Ratio) for monthly cohorts using SubscriptionRetentionSnapshot. Parameterized for 12 months lookback.
  ```kusto
  let initTime = datetime_add('year', -1, startofmonth(now()));
  range x from 0 to 12 step 1
  | extend RangeMonth = datetime_add('month', -1*x, startofmonth(now())), fk = 1
  | join kind=inner (
      SubscriptionRetentionSnapshot
      | where StartDate >= initTime
      | extend StartMonth = startofmonth(StartDate), fk = 1
    ) on fk
  | extend Periods = datetime_diff('month', RangeMonth, StartMonth)
  | where StartMonth <= RangeMonth and EndDate >= RangeMonth
  | summarize Retain = dcount(SubscriptionId) by StartMonth, Periods
  | join kind=inner (
      SubscriptionRetentionSnapshot
      | where StartDate >= initTime
      | extend StartMonth = startofmonth(StartDate)
      | distinct StartMonth, SubscriptionId
      | summarize Total = dcount(SubscriptionId) by StartMonth
    ) on StartMonth
  | project Month = StartMonth, Periods, Total, Retain, Ratio = 1.0*Retain/Total, Category = 'Subscription'
  ```

7. Reasoning Notes (only if uncertain)
- Timezone: Not specified in inputs. Assumed UTC (Kusto default). If data is ingested in local times per region, consider converting to UTC before cross-region aggregations.
- Revenue unit prices: Queries contain sample numeric multipliers for Standard and Premium. Treat these as placeholders (<UnitPriceStandard>, <UnitPricePremium>) and confirm actual pricing/normalization methodology.
- Internal subscriptions function: SignalRTeamInternalSubscriptionIds() used both as a function and as a static list. Ensure you use the appropriate callable function or list for your environment.
- Activity thresholds: LiveRatio categories are inferred from examples (Swift <3 days, Occasional <10, else Dedicate). Confirm thresholds if business logic changes.
- AI cohort detection: Heuristic string matching on ResourceId may include false positives/negatives. Consider curated allowlists/regex or tags when higher precision is required.
- EU/non-EU data completeness: When unioning EU and non-EU tables, lag may differ. Prefer completeness gates per shard or use the conservative EndDate across shards.
- QoS thresholds: 0.999/0.995 appear in examples (Ops/Connectivity). Parameterize as <OpsSlaThreshold>/<ConnSlaThreshold> and validate against current SLO.
- Cached snapshot freshness: Snapshots (Cached_*) are convenient but refresh cadence is not documented here. Validate staleness before OKR reporting.
- Replica normalization: Many queries collapse replicas to the primary ResourceId. Ensure consistency when counting distinct resources across SKU/region pivots.

8. Canonical Tables

## Canonical Tables

This playbook distills how SignalR and Web PubSub analytics queries use core tables and snapshots in the SignalRBI database on cluster signalrinsights.eastus2. It emphasizes OKR/ARR, usage/revenue, service-type growth, and customer/segment analysis. Freshness is generally daily; exact ingestion delay and timezone are unknown, so avoid using “today” until daily jobs complete.

Ordering: High-priority tables first, then Normal, then Low.

---

### Table: BillingUsage_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Daily billing/usage facts at resource granularity. Each row captures Quantity for a ResourceId, SKU, Region, SubscriptionId on Date. Zero rows for a Date/Resource implies no billable usage that day.
- Freshness expectations: Daily pipeline; exact delay unknown. Most analyses window to ≥7–60 days, or cap at last complete day.
- When to use / When to avoid:
  - Use for revenue estimation by SKU (e.g., Standard, Premium) via unit conversion.
  - Use to segment usage by service type (resourceId contains microsoft.signalrservice/signalr or /webpubsub/).
  - Use to derive paid units, total consumption, live resource counts (when joined to ResourceMetrics).
  - Avoid treating Quantity as “connections/messages” (it’s billing units, not runtime telemetry).
- Similar tables & how to choose:
  - ResourceMetrics: runtime telemetry (connections, messages); join on Date/ResourceId for “usage + behavior.”
  - Cached_* snapshots: pre-aggregated weekly/monthly OKR pivots; use for dashboards/OKR views, not per-resource analyses.
- Common Filters:
  - Time: Date >= ago(30–60d), startofweek(), startofmonth().
  - Service: ResourceId has 'microsoft.signalrservice/signalr' or '/webpubsub/'.
  - Exclude internal: SubscriptionId !in (SignalRTeamInternalSubscriptionIds()).
  - SKU in ('Free','Standard','Premium'); exclude 'MessageCount' SKUs in revenue.
- Table columns:
  | Column       | Type     | Description or meaning |
  |--------------|----------|------------------------|
  | Date         | datetime | Usage day (UTC; ingestion timezone unknown). |
  | Region       | string   | Azure region where the usage occurred. |
  | SubscriptionId | string | Azure subscription GUID. |
  | ResourceId   | string   | Full ARM resource ID of SignalR or Web PubSub resource. |
  | SKU          | string   | Billing SKU: Free/Standard/Premium/MessageCount/MessageCountPremium (often filtered). |
  | Quantity     | real     | Billable unit quantity for the day (convert to revenue via unit rates). |
- Column Explain:
  - Date: drives all grouping; align with ResourceMetrics.Date; use startofweek()/startofmonth() for cohorting.
  - ResourceId: determine service type; extract SubscriptionId via split if needed.
  - SKU: used to bucket Free/Standard/Premium and compute revenue.
  - Quantity: foundation for consumption and revenue (with per-SKU multipliers).

---

### Table: MaxConnectionCount_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Daily runtime signal summarizing max connection counts per role/resource; used to validate “active” resources/subscriptions.
- Freshness expectations: Daily; join windows often 28–60 days.
- When to use / When to avoid:
  - Use to filter resources/subscriptions active on a day (MaxConnectionCount > 0).
  - Use as an existence check when counting subscriptions/resources (inner join to ensure live).
  - Avoid as a proxy for revenue; it’s runtime, not billing.
- Similar tables & how to choose:
  - ResourceMetrics: richer telemetry, includes messages and avg connections; choose when you need multi-metric views.
- Common Filters: Date >= ago(60d); join on Date and normalized ResourceId/Role; sometimes project Role = tolower(ResourceId).
- Table columns:
  | Column            | Type     | Description |
  |-------------------|----------|-------------|
  | Date              | datetime | Day of runtime measurement. |
  | Role              | string   | Often normalized ResourceId or role identifier. |
  | SubscriptionId    | string   | Azure subscription GUID. |
  | CustomerType      | string   | Optional classification if present in this table version. |
  | Region            | string   | Azure region. |
  | MaxConnectionCount| long     | Max concurrent connections observed for the day. |
- Column Explain:
  - Role/ResourceId normalization is common (tolower); match BillingUsage_Daily.ResourceId when joining.
  - MaxConnectionCount: booleanization (>0) indicates “active” on given Date.

---

### Table: SubscriptionMappings (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Subscription→customer dimension mapping with segmentation, offers, and billing types; used to enrich facts.
- Freshness expectations: Periodic snapshot; treat as slowly changing dimension but analysts usually use latest mapping at join time.
- When to use / When to avoid:
  - Use to get CustomerType (Internal/External), SegmentName, Offer metadata, BillingType for rollups.
  - Use to count distinct customers via CloudCustomerGuid.
  - Avoid assuming 1:1 stability across time; join on SubscriptionId but be cautious for historical attribution drift.
- Similar tables & how to choose:
  - CustomerModel: richer customer catalog with TP identifiers and names (use for top-customers analysis).
- Common Filters: Typically leftouter join on SubscriptionId; no time filter on this table itself.
- Table columns:
  | Column               | Type   | Description |
  |----------------------|--------|-------------|
  | P360_ID              | string | Customer360 identifier string. |
  | CloudCustomerGuid    | string | Customer GUID for tenant-level counting. |
  | SubscriptionId       | string | Azure subscription GUID (join key). |
  | CustomerType         | string | Internal/External classification. |
  | CustomerName         | string | Friendly customer display name. |
  | SegmentName          | string | Segment name for cohorting. |
  | OfferType            | string | Offer type (e.g., EA, CSP). |
  | OfferName            | string | Offer name. |
  | BillingType          | string | Pay-As-You-Go, Enterprise, etc. |
  | WorkloadType         | string | Workload classification. |
  | S500                 | string | Additional segmentation tag. |
- Column Explain:
  - CustomerType/BillingType/SegmentName frequently pivoted in OKR dashboards.
  - CloudCustomerGuid used to count customers vs subscriptions.

---

### Table: ResourceMetrics (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Daily runtime telemetry aggregates: messages, max/avg connections, errors/operations per ResourceId/Date.
- Freshness expectations: Daily; combine with BillingUsage_Daily for “usage + behavior.”
- When to use / When to avoid:
  - Use for connection/message trends by week/month, service mode and kind.
  - Use to determine HasConnection (MaxConnectionCount > 0).
  - Avoid equating SumMessageCount to billed units (it’s runtime).
- Similar tables & how to choose:
  - MaxConnectionCount_Daily: if only connection activity needed.
  - FeatureTrack* tables: for feature events; use ResourceMetrics for macro metrics instead.
- Common Filters: Date windows (-8 to -26 weeks, or 12 months); ResourceId has 'microsoft.signalrservice/signalr' or '/webpubsub/'.
- Table columns:
  | Column             | Type   | Description |
  |--------------------|--------|-------------|
  | Date               | datetime | Day of telemetry. |
  | Region             | string | Azure region. |
  | ResourceId         | string | Resource ARM ID (lowercased/trimmed for replicas in queries). |
  | SumMessageCount    | real   | Total messages counted (runtime). |
  | MaxConnectionCount | real   | Max concurrent connections (runtime). |
  | AvgConnectionCount | real   | Average concurrent connections (runtime). |
  | SumSystemErrors    | real   | Count of system errors aggregated. |
  | SumTotalOperations | real   | Total operations aggregated. |
- Column Explain:
  - MaxConnectionCount used to determine “live” resources (HasConnection).
  - Region/ResourceId used to segment & join with RPSettingLatest and mappings.

---

### Table: Cached_ZnOKRARR_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Monthly ARR OKR snapshot (zone-level) with per-service ARR values; joined with inline goals in queries.
- Freshness expectations: Periodic snapshot; use with fullouter join against datatable goals.
- When to use / When to avoid:
  - Use for ARR time series vs. targets (SignalR/WebPubSub).
  - Avoid for granular revenue per subscription (use BillingUsage_Daily).
- Similar tables: Cached_DtOKRARR_Snapshot (district/total); EstRevenue snapshots (weekly/monthly).
- Common Filters: TimeStamp >= historical month windows; combine with goals via fullouter join.
- Table columns:
  | Column    | Type     | Description |
  |-----------|----------|-------------|
  | TimeStamp | datetime | Snapshot month end. |
  | SignalR   | real     | ARR metric for SignalR. |
  | WebPubSub | real     | ARR metric for Web PubSub. |
- Column Explain: TimeStamp used to align with goal datatables.

---

### Table: Cached_ZnOKREstRevenueWeekly_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Weekly estimated revenue snapshot by SKU/segment/service (already aggregated).
- Freshness expectations: Weekly; use for OKR reporting not raw revenue.
- When to use / When to avoid:
  - Use for weekly revenue trendlines and segment comparisons.
  - Avoid for per-resource or per-subscription analysis.
- Common Filters: Week windows (e.g., last 8–12 weeks). 
- Table columns:
  | Column    | Type     | Description |
  |-----------|----------|-------------|
  | Week      | datetime | Week end (canonicalized). |
  | SKU       | string   | Free/Standard/Premium. |
  | CustomerType | string| Internal/External. |
  | SegmentName  | string| Segment. |
  | Service   | string   | SignalR/WebPubSub/aggregates (“ JOIN(OR)”). |
  | Income    | real     | Aggregated revenue estimate. |
- Column Explain: Service can be OR-joined categories; Income is already aggregated.

---

### Table: Cached_ZnOKREstRevenueMonthly_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Monthly estimated revenue snapshot by SKU/segment/service.
- Freshness expectations: Monthly; same usage patterns as weekly version.
- Table columns:
  | Column    | Type     | Description |
  |-----------|----------|-------------|
  | Month     | datetime | Month end. |
  | SKU       | string   | SKU bucket. |
  | CustomerType | string| Internal/External. |
  | SegmentName  | string| Segment. |
  | Service   | string   | SignalR/WebPubSub/aggregates. |
  | Income    | real     | Aggregated revenue estimate. |
- Column Explain: Use Month for monthly pivots; combine with goals if necessary.

---

### Table: Cached_ZnOKRSubs_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Monthly subscription-count OKR snapshot; used with WebPubSub goals.
- Freshness expectations: Monthly.
- When to use: Compare actual subs against goal lines for SignalR/WebPubSub.
- Table columns:
  | Column    | Type     | Description |
  |-----------|----------|-------------|
  | TimeStamp | datetime | Month end. |
  | SignalR   | long     | Subscription count for SignalR. |
  | WebPubSub | long     | Subscription count for Web PubSub. |
- Column Explain: Join with goal datatable on TimeStamp.

---

### Table: Cached_CuOKRConsumption_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Monthly consumption OKR snapshot (total and by service).
- Freshness expectations: Monthly.
- When to use: Consumption vs goal (often normalized/rolled up).
- Table columns:
  | Column    | Type     | Description |
  |-----------|----------|-------------|
  | TimeStamp | datetime | Month end. |
  | Consumption | real   | Total consumption metric. |
  | SignalR   | real     | SignalR portion. |
  | WebPubSub | real     | WebPubSub portion. |
- Column Explain: Often unioned with datatable goals to compute gaps.

---

### Table: Cached_CuOKRConsumptionWeekly_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Weekly consumption OKR snapshot by SKU/segment/service.
- Freshness expectations: Weekly.
- Table columns:
  | Column    | Type     | Description |
  |-----------|----------|-------------|
  | Week      | datetime | Week marker. |
  | SKU       | string   | SKU bucket. |
  | CustomerType | string| Internal/External. |
  | SegmentName  | string| Segment. |
  | Service   | string   | SignalR/WebPubSub/aggregates. |
  | Consumption | real   | Aggregated consumption (e.g., normalized). |
- Column Explain: Parallel to revenue snapshots but for consumption.

---

### Table: Cached_CuOKRConsumptionMonthly_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Monthly consumption OKR snapshot.
- Freshness expectations: Monthly.
- Table columns:
  | Column    | Type     | Description |
  |-----------|----------|-------------|
  | Month     | datetime | Month marker. |
  | SKU       | string   | SKU bucket. |
  | CustomerType | string| Internal/External. |
  | SegmentName  | string| Segment. |
  | Service   | string   | Service or OR-join aggregate. |
  | Consumption | real   | Aggregated consumption. |
- Column Explain: Use Month for long-horizon views.

---

### Table: Cached_DtOKRARR_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Total-level ARR OKR monthly snapshot (across services).
- Freshness expectations: Monthly.
- When to use: Total ARR vs. target (no per-service breakdown).
- Table columns:
  | Column    | Type     | Description |
  |-----------|----------|-------------|
  | TimeStamp | datetime | Month end. |
  | SignalR   | real     | ARR (label name suggests total; column present per schema). |
  | WebPubSub | real     | ARR for WebPubSub (if present; schema includes service columns). |
  | total     | real     | Total ARR (if populated). |
- Column Explain: Analysts often compute TotalGoal via datatable and compare.

---

### Table: Cached_DtOKREstRevenueWeekly_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Weekly estimated revenue, total-level, by SKU/usage type (UsageType is often derived post-join).
- Freshness expectations: Weekly.
- Table columns:
  | Column    | Type     | Description |
  |-----------|----------|-------------|
  | Week      | datetime | Week end. |
  | SKU       | string   | SKU bucket. |
  | UsageType | string   | Derived usage (Internal vs billing type). |
  | SegmentName | string | Segment name. |
  | Service   | string   | Service line. |
  | Income    | real     | Revenue estimate. |

---

### Table: Cached_DtOKREstRevenueMonthly_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Monthly estimated revenue, total-level.
- Freshness expectations: Monthly.
- Table columns:
  | Column    | Type     | Description |
  |-----------|----------|-------------|
  | Month     | datetime | Month end. |
  | SKU       | string   | SKU bucket. |
  | UsageType | string   | Usage type. |
  | SegmentName | string | Segment name. |
  | Service   | string   | Service line. |
  | Income    | real     | Revenue estimate. |

---

### Table: Cached_DtOKRSubsWeekly_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Weekly subscription counts snapshot (OKR) at total-level by SKU/UsageType/Service; used in cohorting.
- Freshness expectations: Weekly.
- Table columns:
  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Week          | datetime | Week end. |
  | SKU           | string   | SKU bucket. |
  | UsageType     | string   | Derived usage type. |
  | Service       | string   | Service or aggregate flag. |
  | SubscriptionCnt | int    | Distinct subscription count (approx dcount). |
  | SegmentName   | string   | Segment name. |

---

### Table: Cached_DtOKRSubsMonthly_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Monthly subscription counts snapshot at total level.
- Freshness expectations: Monthly.
- Table columns:
  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Month         | datetime | Month end. |
  | SKU           | string   | SKU bucket. |
  | UsageType     | string   | Derived usage. |
  | SegmentName   | string   | Segment name. |
  | Service       | string   | Service or aggregate. |
  | SubscriptionCnt | int    | Distinct subscription count. |

---

### Table: CustomerModel (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Extended customer catalog with TP identifiers, subscription friendliness and names; used for top customers and Cx links.
- Freshness expectations: Periodic; use latest for enrichment.
- When to use: Enrich top-subscriptions snapshots (Revenue/Connections/Messages) with customer identity and C360 URLs.
- Table columns:
  | Column                     | Type   | Description |
  |----------------------------|--------|-------------|
  | C360_ID                    | string | Customer360 ID. |
  | CustomerName               | string | Customer display name. |
  | CloudCustomerGuid          | string | Tenant GUID. |
  | CloudCustomerName          | string | Tenant name. |
  | TPID                       | int    | Tenant P360 numeric ID. |
  | TPName                     | string | Tenant P360 display name. |
  | CustomerType               | string | Internal/External. |
  | SubscriptionId             | string | Azure subscription GUID. |
  | FriendlySubscriptionName   | string | Subscription display name. |
  | WorkloadType               | string | Workload classification. |
  | BillingType                | string | EA/CSP/… |
  | OfferType                  | string | Offer type. |
  | OfferName                  | string | Offer name. |
  | CurrentSubscriptionStatus  | string | Subscription state. |
  | SegmentName                | string | Segment. |
  | P360_ID                    | string | P360 ID string (duplicate logical field). |
  | P360_CustomerDisplayName   | string | P360 display name. |
  | SubscriptionCreatedDate    | datetime | Creation date. |
  | S500                       | string | Segmentation tag. |
- Column Explain:
  - TPID/TPName used to generate C360 links.
  - SubscriptionId used to join with TopSubscriptions and BillingUsage_Daily.

---

### Table: Cached_TopSubscriptions_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Rolling top subscriptions snapshot with revenue/max connections/message counts and time window (StartDate/EndDate).
- Freshness expectations: Rolling last ~28–29 days.
- When to use: Top subscriptions detail and daily metrics expansion by category (PaidUnits/Revenue/Messages/Connections/Resources).
- Table columns:
  | Column          | Type     | Description |
  |-----------------|----------|-------------|
  | SubscriptionId  | string   | Subscription GUID. |
  | Revenue         | real     | Revenue in window. |
  | MaxConnection   | long     | Max connections in window. |
  | MessageCount    | long     | Messages in window. |
  | StartDate       | datetime | Window start. |
  | EndDate         | datetime | Window end. |
  | TopRevenue      | real     | Rank/score value for revenue. |
  | TopConnection   | long     | Rank/score value for connections. |
  | TopMessageCount | long     | Rank/score value for messages. |
  | Rate            | real     | Derived rate/score. |
  | Service         | string   | SignalR/WebPubSub. |
- Column Explain: Join back to ResourceMetrics and BillingUsage_Daily to expand daily series per SubscriptionId.

---

### Table: Cached_SubsTotalWeekly_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Weekly totals snapshot per subscription for cohorting.
- Freshness expectations: Weekly.
- When to use: Weekly subscription/customer counts by region/SKU/customer/hasConnection/liveRatio.
- Table columns:
  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Week          | datetime | Week marker. |
  | ServiceType   | string   | SignalR or WebPubSub. |
  | SubscriptionId| string   | Subscription GUID. |
  | Region        | string   | Region. |
  | SKU           | string   | SKU. |
  | HasConnection | bool     | True if runtime connection activity observed. |
  | LiveRatio     | string   | Activity band (Swift/Occasional/…). |
- Column Explain: Often aggregated with join to SubscriptionMappings to derive counts by CustomerType and cohorts (e.g., LiveRatio).

---

### Table: Cached_SubsTotalMonthly_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: High
- What this table represents: Monthly totals snapshot per subscription for cohorting (monthly grain).
- Freshness expectations: Monthly.
- Table columns:
  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Month         | datetime | Month marker. |
  | ServiceType   | string   | Service. |
  | SubscriptionId| string   | Subscription GUID. |
  | Region        | string   | Region. |
  | SKU           | string   | SKU. |
  | HasConnection | bool     | Activity flag. |
  | LiveRatio     | string   | Activity band. |
- Column Explain: Paired with CustomerFlow/SubscriptionFlow monthly for cohort dashboards.

---

### Table: OperationQoS_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Low
- What this table represents: Daily QoS uptime summary by environment/role with totalUpTimeSec/totalTimeSec for SLA computations.
- Freshness expectations: Daily.
- When to use: Operation QoS trends (rolling 7/28 day windows), SLA attainment by region/overall.
- Common Filters: env_time > ago(30–60d); resourceId has 'microsoft.signalrservice/signalr' or contains 'webpubsub'.
- Table columns:
  | Column               | Type     | Description |
  |----------------------|----------|-------------|
  | env_name             | string   | Environment name. |
  | env_time             | datetime | Day marker. |
  | resourceId           | string   | Resource identifier. |
  | env_cloud_role       | string   | Cloud role. |
  | env_cloud_roleInstance | string | Instance. |
  | env_cloud_environment| string   | Cloud env. |
  | env_cloud_location   | string   | Region. |
  | env_cloud_deploymentUnit | string| DU. |
  | totalUpTimeSec       | long     | Uptime seconds. |
  | totalTimeSec         | long     | Total seconds. |
- Column Explain: Qos = sum(totalUpTimeSec)/sum(totalTimeSec) over groupings.

---

### Table: ConnectivityQoS_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Low
- What this table represents: Daily connectivity QoS (methodology similar to OperationQoS_Daily).
- Common usage: Connectivity SLA attainment (>=0.995/0.999 thresholds).
- Columns: Same structure as OperationQoS_Daily (env_* and totals).

---

### Table: ManageRPQosDaily (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Management plane API QoS counts by Date/ApiName/Region/Result; used for RP success rate.
- Common filters: ApiName exclusions (UNCATEGORY/INVALID/etc.), CustomerType in ('SignalR','WebPubSub','').
- Table columns:
  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Date          | datetime | Day. |
  | ApiName       | string   | RP operation name. |
  | SubscriptionId| string   | Subscription. |
  | CustomerType  | string   | Product line or blank. |
  | Region        | string   | Region. |
  | Result        | string   | Success/Timeout/CustomerError/etc. |
  | Count         | long     | Request counts. |

---

### Table: ManageResourceTags (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Control-plane resource tag/operation events.
- Usage: Subscription/resource counts by request name/method; segment by CustomerType via join to SubscriptionMappings.
- Table columns:
  | Column      | Type     | Description |
  |-------------|----------|-------------|
  | Date        | datetime | Day. |
  | SubscriptionId | string| Subscription. |
  | ResourceId  | string   | Resource ARM ID. |
  | RequestName | string   | Operation name. |
  | Tags        | string   | Tags/method payload. |
  | Count       | long     | Event count. |

---

### Table: RuntimeRequestsGroups_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Low
- What this table represents: Runtime grouped scenarios (non-transport), counts per category/metrics.
- Usage: Feature/Scenario usage ranking with thresholds (ResourceCount>10, RequestCount>200).
- Table columns:
  | Column       | Type     | Description |
  |--------------|----------|-------------|
  | Date         | datetime | Day. |
  | Category     | string   | Scenario group (RestApiScenario/…). |
  | Metrics      | string   | Scenario/feature key. |
  | ResourceCount| long     | Distinct resources. |
  | RequestCount | long     | Requests total. |

---

### Table: RuntimeRequestsGroups_EU_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Low
- Same schema and usage as RuntimeRequestsGroups_Daily for EU partitioning.

---

### Table: RuntimeTransport_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Low
- What this table represents: Transport-level runtime metrics by Framework/Transport (e.g., WebSockets/LongPolling).
- Usage: Append transport metrics into scenario unions.
- Table columns:
  | Column        | Type   | Description |
  |---------------|--------|-------------|
  | Date          | datetime | Day. |
  | Feature       | string | Feature flag. |
  | Transport     | string | Transport type. |
  | Framework     | string | Framework identifier. |
  | ResourceId    | string | Resource ARM ID. |
  | SubscriptionId| string | Subscription GUID. |
  | RequestCount  | long   | Requests count. |

---

### Table: RuntimeTransport_EU_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Low
- Same schema and usage as RuntimeTransport_Daily for EU partitioning.

---

### Table: ConnectionMode_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Daily connection mode breakdown per resource (ServerlessConnection vs ProxyConnection) with ServiceMode.
- Commonly used to compute IsServerless/IsServerMode at subscription level.
- Table columns:
  | Column              | Type   | Description |
  |---------------------|--------|-------------|
  | Date                | datetime | Day. |
  | ResourceId          | string | Resource ARM ID. |
  | ServerlessConnection| long   | Serverless connection count. |
  | ProxyConnection     | long   | Server mode connection count. |
  | ServiceMode         | string | Reported service mode. |

---

### Table: KPIv2019 (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Legacy KPI series (pivoted in queries).
- Table columns:
  | Column            | Type     | Description |
  |-------------------|----------|-------------|
  | Date              | datetime | Day. |
  | SubscriptionCount | long     | Count metric. |
  | ResourceCount     | long     | Count metric. |

---

### Table: ChurnCustomers_Monthly (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Monthly churn stats by service type.
- Table columns:
  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Month         | datetime | Month. |
  | ServiceType   | string   | SignalR/WebPubSub. |
  | Total         | long     | Total customers. |
  | Churn         | long     | Churn count. |
  | Standard      | long     | Standard-tier customers. |
  | StandardChurn | long     | Churn in Standard. |
  | RunDay        | datetime | Run timestamp. |

---

### Table: ConvertCustomer_Weekly (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Weekly conversion counts between tiers.
- Table columns:
  | Column            | Type     | Description |
  |-------------------|----------|-------------|
  | Week              | datetime | Week. |
  | ServiceType       | string   | Service. |
  | FreeToStandard    | long     | Conversion count. |
  | TotalCustomers    | long     | Total customers metric. |
  | StandardCustomers | long     | Count. |
  | RunDay            | datetime | Run timestamp. |
  | FreeToPaid        | long     | Count. |
  | StandardToPremium | long     | Count. |
  | FreeToPremium     | long     | Count. |
  | PremiumCustomers  | long     | Count. |

---

### Table: OKRv2021 (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Generic OKR series: Date/Category/Value; pivoted to wide forms in dashboards.
- Table columns:
  | Column   | Type     | Description |
  |----------|----------|-------------|
  | Date     | datetime | Measurement date. |
  | Category | string   | Metric category. |
  | Value    | real     | Metric value. |

---

### Table: RuntimeResourceTags_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Per-resource flags from resource tags and classification (AppService/StaticApps/Samples/Proxy/etc.).
- Table columns:
  | Column         | Type     | Description |
  |----------------|----------|-------------|
  | Date           | datetime | Day. |
  | ResourceId     | string   | ARM ID. |
  | SubscriptionId | string   | Subscription GUID. |
  | ServiceType    | string   | SignalR/WebPubSub. |
  | IsAppService   | bool     | App Service integration flag. |
  | IsStaticApps   | bool     | Static Web Apps integration flag. |
  | IsSample       | bool     | Sample usage flag. |
  | IsProxy        | bool     | Proxy mode flag. |
  | HasFailure     | bool     | Failure observed. |
  | HasSuccess     | bool     | Success observed. |
  | Extra          | string   | JSON extras. |

---

### Table: FeatureTrack_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Daily feature usage counts by Feature and ResourceId.
- Table columns:
  | Column       | Type     | Description |
  |--------------|----------|-------------|
  | Date         | datetime | Day. |
  | Feature      | string   | Feature identifier. |
  | ResourceId   | string   | ARM ID. |
  | SubscriptionId | string | Subscription GUID. |
  | RequestCount | long     | Requests count. |

---

### Table: FeatureTrackV2_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- Enhanced feature tracking including Category and Properties.
- Columns:
  | Column       | Type     | Description |
  |--------------|----------|-------------|
  | Date         | datetime | Day. |
  | Feature      | string   | Feature. |
  | Category     | string   | Feature group. |
  | ResourceId   | string   | ARM ID. |
  | SubscriptionId | string | Subscription GUID. |
  | Properties   | string   | JSON properties. |
  | RequestCount | long     | Count. |

---

### Table: FeatureTrackV2_EU_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- EU partition of FeatureTrackV2; same schema as above.

---

### Table: FeatureTrack_AutoScale_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- Tracks auto-scale feature usage per resource/day.
- Columns:
  | Column       | Type     | Description |
  |--------------|----------|-------------|
  | Date         | datetime | Day. |
  | Region       | string   | Region. |
  | ResourceId   | string   | ARM ID. |
  | SubscriptionId | string | Subscription GUID. |
  | RequestCount | long     | Count. |

---

### Table: RPSettingLatest (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Latest RP settings per resource (state/mode/security toggles); Extras contains JSON like socketIO.serviceMode, isAspire flags.
- Usage: Join with ResourceMetrics/BillingUsage_Daily to segment by Kind/ServiceMode and detect Aspire/SocketIO usage.
- Columns:
  | Column                 | Type   | Description |
  |------------------------|--------|-------------|
  | ResourceId             | string | ARM ID. |
  | Region                 | string | Region. |
  | SKU                    | string | SKU. |
  | Kind                   | string | Service kind (WebPubSub/SocketIO). |
  | State                  | string | RP state. |
  | ServiceMode            | string | Server/Serverless/etc. |
  | IsUpstreamSet          | bool   | Upstream configured. |
  | IsEventHandlerSet      | bool   | Event handler configured. |
  | EnableTlsClientCert    | bool   | TLS client cert enabled. |
  | IsPrivateEndpointSet   | bool   | Private endpoint set. |
  | EnablePublicNetworkAccess | bool| Public network enabled. |
  | DisableLocalAuth       | bool   | Local auth disabled. |
  | DisableAadAuth         | bool   | AAD auth disabled. |
  | IsServerlessTimeoutSet | bool   | Serverless timeout configured. |
  | AllowAnonymousConnect  | bool   | Anonymous connect allowed. |
  | EnableRegionEndpoint   | bool   | Region endpoint enabled. |
  | ResourceStopped        | bool   | Resource stopped flag. |
  | EnableLiveTrace        | bool   | Live trace enabled. |
  | EnableResourceLog      | bool   | Resource log enabled. |
  | LastUpdated            | datetime | Last update time. |
  | Extras                 | string | JSON extras; contains isAspire/socketIO settings. |

---

### Table: Cached_ResourceFlow_Snapshot (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Cached weekly/monthly resource flow aggregates with partition markers (Week/Month) and category slices.
- Columns:
  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Category      | string   | Flow category. |
  | Region        | string   | Region. |
  | SKU           | string   | SKU. |
  | HasConnection | bool     | Activity flag. |
  | LiveRatio     | string   | Activity band. |
  | ResourceCnt   | long     | Count. |
  | Date          | datetime | Partitioned date (renamed to Week/Month in queries). |
  | ServiceType   | string   | SignalR/WebPubSub. |
  | Partition     | string   | 'Week' or 'Month'. |

---

### Table: SubscriptionRetentionSnapshot (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Subscription retention intervals with StartDate/EndDate; used to compute retention cohorts.
- Columns:
  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | SubscriptionId| string   | Subscription GUID. |
  | StartDate     | datetime | Start of retention interval. |
  | EndDate       | datetime | End of retention interval (inclusive). |

---

### Table: CustomerRetentionSnapshot (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- Retention intervals at customer (C360_ID) level.
- Columns: C360_ID (string), StartDate (datetime), EndDate (datetime).

---

### Table: ResourceRetentionSnapshot (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- Retention intervals at ResourceId level.
- Columns: ResourceId (string), StartDate (datetime), EndDate (datetime).

---

### Table: DeleteSurvey (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Deletion survey responses for SignalR (reason/feedback).
- Columns:
  | Column     | Type     | Description |
  |------------|----------|-------------|
  | TIMESTAMP  | datetime | Event time. |
  | Deployment | string   | Deployment environment. |
  | resourceId | string   | Resource involved. |
  | reason     | string   | Reason text/category. |
  | feedback   | string   | Free-text feedback. |
  | objectId   | string   | User/object identifier. |
  | sessionId  | string   | Session identifier. |

---

### Table: FeedbackSurvey (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Customer feedback survey (CES/CVA).
- Columns:
  | Column   | Type  | Description |
  |----------|-------|-------------|
  | TimeStamp| datetime | Event time. |
  | CESValue | int   | Customer Effort Score. |
  | CVAValue | int   | Customer Value Added. |
  | Comments | string| Free-text comments. |

---

### Table: WebTools_Raw (ddtelinsights/<unknown-db>)
- Priority: Low
- What this table represents: VS/WebTools telemetry used for SignalR developer funnel tracking, including detection/config/publish/provisioning events.
- Freshness expectations: Near-daily; cross-cluster source not available via this environment.
- Schema: Cross-cluster; schema could not be retrieved here. Use the source ddtelinsights cluster to inspect schema before building queries.
- When to use / When to avoid:
  - Use to measure developer detection, suggestions, publish events, provisioning outcomes.
  - Avoid for business KPIs or billing metrics; use BillingUsage_Daily/ResourceMetrics instead.
- Common Filters: AdvancedServerTimestampUtc time ranges; EventName filters; Properties/Measures keys.

---

### Table: KPI_AWPS (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Web PubSub KPI counts (subscription/resource).
- Columns:
  | Column            | Type     | Description |
  |-------------------|----------|-------------|
  | Date              | datetime | Day. |
  | SubscriptionCount | long     | KPI count. |
  | ResourceCount     | long     | KPI count. |

---

### Table: OKRv2021_AWPS (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: OKR series for AWPS (WebPubSub).
- Columns: Date (datetime), Category (string), Value (real).

---

### Table: OKRv2021_SocketIO (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: OKR series for Socket.IO flavor.
- Columns: Date (datetime), Category (string), Value (real).

---

### Table: DeleteSurveyWebPubSub (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- Mirrors DeleteSurvey for WebPubSub resources.
- Columns: TIMESTAMP, Deployment, resourceId, reason, feedback, objectId, sessionId.

---

### Table: ResourceFlow_Weekly (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this represents: Function output (flow) materialized via function; schema observed with getschema.
- Columns:
  | Column      | Type     | Description |
  |-------------|----------|-------------|
  | Week        | datetime | Week. |
  | Category    | string   | Flow category. |
  | Region      | string   | Region. |
  | SKU         | string   | SKU. |
  | HasConnection | bool   | Activity flag. |
  | LiveRatio   | string   | Activity band. |
  | ResourceCnt | long     | Count. |

---

### Table: ResourceFlow_Monthly (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- Columns: Month (datetime), Category (string), Region (string), SKU (string), HasConnection (bool), LiveRatio (string), ResourceCnt (long).

---

### Table: SubscriptionFlow_Weekly (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- Columns:
  | Column        | Type     |
  |---------------|----------|
  | Week          | datetime |
  | Category      | string   |
  | Region        | string   |
  | SKU           | string   |
  | HasConnection | bool     |
  | LiveRatio     | string   |
  | CustomerType  | string   |
  | OfferName     | string   |
  | OfferType     | string   |
  | BillingType   | string   |
  | SubscriptionCnt | long   |

---

### Table: SubscriptionFlow_Monthly (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- Columns: Month, Category, Region, SKU, HasConnection, LiveRatio, CustomerType, OfferName, OfferType, BillingType, SubscriptionCnt.

---

### Table: CustomerFlow_Weekly (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- Columns:
  | Column       | Type     |
  |--------------|----------|
  | Week         | datetime |
  | Category     | string   |
  | Region       | string   |
  | SKU          | string   |
  | HasConnection| bool     |
  | LiveRatio    | string   |
  | CustomerType | string   |
  | SegmentionType | string |
  | CustomerCnt  | long     |

---

### Table: CustomerFlow_Monthly (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- Columns: Month, Category, Region, SKU, HasConnection, LiveRatio, CustomerType, SegmentionType, CustomerCnt.

---

### Table: KPI_SocketIO (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- What this table represents: Socket.IO KPIs (subscription/resource counts).
- Columns: Date (datetime), SubscriptionCount (long), ResourceCount (long).

---

### Table: AwpsRuntimeRequestsGroups_Daily (signalrinsights.eastus2/SignalRBI)
- Priority: Low
- What this represents: WebPubSub runtime grouped requests; used to normalize metrics naming (e.g., v2021-…).
- Columns: Date (datetime), Category (string), Metrics (string), ResourceCount (long), RequestCount (long).

---

### Table: AwpsRetention_SubscriptionSnapshot (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- WebPubSub subscription retention intervals; used to compute M/W retention cohorts.
- Columns: SubscriptionId (string), StartDate (datetime), EndDate (datetime).

---

### Table: AwpsRetention_CustomerSnapshot (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- WebPubSub customer retention intervals (C360_ID).
- Columns: C360_ID (string), StartDate (datetime), EndDate (datetime).

---

### Table: AwpsRetention_ResourceSnapshot (signalrinsights.eastus2/SignalRBI)
- Priority: Normal
- WebPubSub resource retention intervals (ResourceId).
- Columns: ResourceId (string), StartDate (datetime), EndDate (datetime).

---

## Shared Practices and Patterns

- Freshness and time windows:
  - Use end-of-day/week/month anchors via startofweek() / startofmonth() and avoid including “today” unless pipelines are confirmed complete.
  - For “current” periods, many queries compute Current = toscalar(table | top 1 by Date desc) and then derive rolling windows (7d/28d).

- Excluding internal usage:
  - Always filter SubscriptionId !in (SignalRTeamInternalSubscriptionIds()) or join-derived UsageType to separate Internal vs external billing.

- Service-type detection:
  - SignalR: ResourceId has 'microsoft.signalrservice/signalr' or '/signalr/'.
  - Web PubSub: ResourceId has 'microsoft.signalrservice/webpubsub' or '/webpubsub/'.
  - Socket.IO: RPSettingLatest: Kind == 'SocketIO' and Extras parsing.

- Revenue computation:
  - Don’t hardcode prices in production queries. Abstraction used in samples:
    - Standard unit price ~ <UnitPriceStandard>
    - Premium unit price ~ <UnitPricePremium>
    - Free = 0
  - Revenue = UnitPrice(SKU) * Quantity

- Cohort and activity flags:
  - Active resource: MaxConnectionCount > 0 (from ResourceMetrics/MaxConnectionCount_Daily).
  - LiveRatio categories: derived from ActiveDays thresholds (e.g., Swift, Occasional, Dedicate) when summarizing over week/month.

- Join order tips:
  - Use leftouter when enriching facts with SubscriptionMappings/CustomerModel to avoid row-loss.
  - Normalize ResourceId/Role to lower() to avoid mismatched joins.
  - For snapshots, pivot/pack/mv-expand patterns are used to create Service breakdowns (JOIN(OR)/JOIN(AND) labels).

- Performance defaults:
  - Start with narrower windows (last 8–12 weeks or last 6–12 months) and top-N aggregations.
  - Leverage summarize with dcount(…, accuracy) where used (e.g., dcount(…, 4)) for performance vs accuracy trade-offs.

- Cross-cluster data:
  - WebTools_Raw lives on ddtelinsights; inspect schema on that cluster before adding new fields/filters.

This document covers all referenced high-, normal-, and low-priority tables and their schemas where available from the configured environment. For any newly added views/functions, follow the same patterns: define time windows conservatively, normalize ResourceId, exclude internal subscriptions, and enrich with SubscriptionMappings/CustomerModel as needed.