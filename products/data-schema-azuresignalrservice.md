# AzureSignalRService - Product and Data Overview Template

## 1. Product Overview

AzureSignalRService covers both Azure SignalR Service and Azure Web PubSub. This onboarding schema equips PMAgent to correctly interpret telemetry, usage, QoS, feature adoption, and customer cohorts for these services. It includes conventions for time alignment, completeness gates, and standard join/aggregation patterns across daily fact tables and hourly diagnostics. The scope primarily targets the signalrinsights.eastus2 cluster and SignalRBI database.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**:
AzureSignalRService (covers both Azure SignalR Service and Azure Web PubSub)
- **Product Nick Names**: 
**[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations.
- **Kusto Cluster**:
signalrinsights.eastus2
- **Kusto Database**:
SignalRBI
- **Access Control**:
**[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed **groups/users** here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

# Azure SignalR Service + Web PubSub Kusto Query Playbook

## Overview
- Product: AzureSignalRService (covers both Azure SignalR Service and Azure Web PubSub)
- Summary: Power Query M blocks defining Azure Data Explorer (KQL) queries for Azure SignalR Service and Azure Web PubSub, covering QoS (operation/connectivity), service usage, billing/revenue, subscriptions/customers retention and category flows, features usage (including SocketIO, AutoScale, Aspire), runtime/ARM/VS telemetry, and error diagnostics. Main execution target is the signalrinsights.eastus2 cluster and SignalRBI database.
- Primary cluster/database:
  - Cluster: signalrinsights.eastus2
  - Database: SignalRBI
- Alternates observed:
  - ddtelinsights (for WebTools_Raw developer telemetry)
  - armprodgbl.eastus (ARM Requests/HttpIncomingRequests; typically accessed via a union helper)

## Conventions & Assumptions

### Time semantics
- Observed timestamp columns by source:
  - Operation/Connectivity QoS: env_time (datetime); often binned to day/week/month
  - Daily fact tables (usage/billing/feature/runtime): Date (datetime)
  - Hourly errors/exceptions: DateHour (string/datetime-like), Timestamp (datetime)
  - Developer telemetry (WebTools_Raw): AdvancedServerTimestampUtc (datetime)
- Canonical Time Column: Date
  - Align non-Date tables to Date with explicit aliasing:
    - QoS tables: project-rename Date = env_time
    - Hourly sources: project Date = startofday(Timestamp) or Date = startofday(todatetime(DateHour))
    - Developer telemetry: project Date = startofday(AdvancedServerTimestampUtc)
- Typical windows and binning
  - ago windows: 10d, 30d, 43d, 60d, 61d
  - Week bins: startofweek(Date)
  - Month bins: startofmonth(Date)
  - Day bins: startofday(...)
- Timezone: Not specified; assume UTC.

### Freshness & Completeness Gates
- Daily ingestion can lag; current day may be incomplete. Queries commonly gate to a last “complete” day using sentinel slices (regions).
- Multi-slice completeness gate pattern (observed):
  - Require ≥N regions to report for the day, then pick the latest such day.
  - Example patterns:
    - Using two regions:
      kusto
      let EndDate = toscalar(
        BillingUsage_Daily
        | where Date > ago(61d) and Region in ('australiaeast', 'westeurope')
        | summarize counter = dcount(Region) by Date
        | where counter >= 2
        | top 1 by Date desc
        | project Date
      );
    - Using broad estate (e.g., ≥38 regions):
      kusto
      let EndDate = toscalar(
        BillingUsage_Daily
        | where Date > ago(10d)
        | summarize counter = dcount(Region) by Date
        | where counter >= 38
        | top 1 by Date desc
        | project Date
      );
- If freshness is unknown, consider excluding today and use startofweek(now())-1d or startofmonth(now())-1d closures.

### Joins & Alignment
- Frequent keys:
  - ResourceId (string path; includes provider and may include /replicas/)
  - SubscriptionId
  - Date (datetime) after alignment
  - Region (string)
  - For QoS: env_cloud_location, env_cloud_role (resource), env_cloud_roleInstance (pod)
- Join kinds:
  - leftouter for enrichment (RPSettingLatest, SubscriptionMappings)
  - inner for cohort filters (e.g., allowlisted ApiName, SKU presence)
  - fullouter to merge KPI snapshots with goals baselines
- Post-join hygiene:
  - Normalize resource casing and replicas:
    kusto
    | extend ResourceId = tolower(ResourceId)
    | extend ResourceId = iif(ResourceId has '/replicas/', substring(ResourceId, 0, indexof(ResourceId, '/replicas/')), ResourceId)
  - Resolve duplicate columns:
    - Prefer $left/$right scoping in join
    - project-away unnecessary duplicates
  - Coalesce normalized fields when mixed sources:
    kusto
    | extend Region = coalesce(Region1, Region)

### Filters & Idioms
- Common predicates:
  - Resource scoping:
    - SignalR resources: ResourceId has 'microsoft.signalrservice/signalr'
    - Web PubSub resources: ResourceId has 'microsoft.signalrservice/webpubsub'
  - Case normalization: tolower(ResourceId) before joins
  - Text predicates: has and contains used; prefer has for word-boundary semantics on provider paths
- Default exclusions:
  - Exclude internal/test subscriptions:
    - SignalRTeamInternalSubscriptionIds or SignalRTeamInternalSubscriptionIds()
- API cohorts:
  - Exclude management noise:
    - ApiName !in ('UNCATEGORY', 'Internal-ACIS')
    - ApiName !in ('INVALID', 'GetResource', 'OperationList', 'OperationResult', 'UpdateSubscription')
    - ApiName !contains 'acs' and !contains 'acis'
  - Allowlist via computed set then inner join:
    kusto
    let AllowedApis = MaterializedAPITable
      | where <filters>
      | distinct ApiName;
    ManageRPQosDaily
      | join kind=inner AllowedApis on ApiName
- Replicas handling:
  - Normalize to primary resource for rollups (strip '/replicas/...')

### Cross-cluster/DB & Sharding
- Cross-source qualification patterns (generic):
  - cluster('armprodgbl.eastus').database('<db>').Requests
  - cluster('ddtelinsights').database('<db>').WebTools_Raw
  - Use helper functions when provided (e.g., Unionizer('Requests','HttpIncomingRequests')) to mask cross-cluster details.
- Sharded regional tables:
  - EU shards provided separately; normalize via union then aggregate:
    kusto
    let ft = FeatureTrackV2_Daily | project Date, ResourceId, SubscriptionId, Category, Feature, RequestCount;
    let ft_eu = FeatureTrackV2_EU_Daily | project Date, ResourceId, SubscriptionId, Category, Feature, RequestCount;
    ft
    | union ft_eu
    | summarize RequestCount = sum(RequestCount) by Date, ResourceId, SubscriptionId, Category, Feature

### Table classes
- Fact (daily/events): BillingUsage_Daily, MaxConnectionCount_Daily, SumMessageCount_Daily, AvgConnectionCountEP_Daily, ConnectionMode_Daily, FeatureTrack*_Daily, Runtime*_*_Daily, ConnectionQoS_Daily, ManageRPQosDaily, ManageResourceTags, ErrorsAbortedConnections_Daily
- Snapshot (latest or cached aggregates): Cached_*_Snapshot, *RetentionSnapshot, CustomerModel
- Pre-aggregated/KPI: KPIv2019, OKRv2021*, KPI_AWPS, KPI_SocketIO
- Usage guidance:
  - Use facts for precise time-series and joins across entities
  - Use snapshots for curated, ready-to-plot dashboards and expensive cohort rollups
  - Avoid mixing snapshots and facts in the same series unless time is explicitly aligned

## Entity & Counting Rules (Core Definitions)

- Entity model:
  - Resource (ResourceId) → Subscription (SubscriptionId) → Customer (CloudCustomerGuid)
  - Customer metadata via SubscriptionMappings and CustomerModel (CustomerType, SegmentName, CloudCustomerName, TPName, TPID, OfferName/Type, BillingType)
- Counting rules:
  - Distinct counts use dcount with reliability parameter:
    - dcount(EntityId, 3) or dcount(EntityId, 4) for stability
  - Cohorts:
    - HasConnection: max(MaxConnectionCount) > 0 over period
    - LiveRatio classification (activity days within period):
      - ActiveDays < 3 → 'Swift'
      - ActiveDays < 10 → 'Occasional'
      - Else → 'Dedicate'
- Business definitions:
  - Operation QoS: Qos = sum(totalUpTimeSec) / sum(totalTimeSec); SLA attainment threshold commonly 0.999
  - Connectivity QoS: Qos = sum(totalUpTimeSec) / sum(totalTimeSec); SLA attainment threshold commonly 0.995
  - ManageRP QoS (SignalR): success cohort includes Result in ('Success', 'Timeout', 'CustomerError')
  - ManageRP QoS (WebPubSub): success cohort often Result == 'Success' (more strict)
  - Connection QoS:
    - Qos = sum(SuccessConnection) / sum(TotalConnection)
    - ServiceQos = 1.0 - sum(ServiceAbortedConnection)/sum(TotalConnection)
  - Revenue/Usage normalization:
    - Avoid hardcoding; parameterize unit prices:
      kusto
      let StandardUnitPrice = 1.61;
      let PremiumUnitPrice = 2.0;
      | extend Revenue = case(SKU=='Free', 0.0, SKU=='Standard', StandardUnitPrice, SKU=='Premium', PremiumUnitPrice, 1.0) * Quantity

## Canonical Tables

Note: Columns/types are derived from observed usage in queries (schema may contain more fields).

### OperationQoS_Daily (signalrinsights.eastus2/SignalRBI)
- Represents: Daily operation QoS fact per resource/region/pod. Zero rows imply no data; expect daily freshness with possible lag.
- When to use:
  - Compute operation SLA/QoS by day/week/month
  - SlaAttainment by region across resources
  - Roll-forward rolling-7/28 QoS series
- When to avoid:
  - Billing/usage joins without aligning to Date
  - Latest-day dashboards without completeness gating
- Similar tables: ConnectivityQoS_Daily (connectivity QoS). Use both for a full QoS picture.
- Common Filters (important):
  - env_time windows (ago/startofweek/startofmonth)
  - resourceId has 'microsoft.signalrservice/signalr' or contains 'webpubsub'
- Columns

  | Column                 | Type     | Description or meaning |
  |------------------------|----------|------------------------|
  | env_time               | datetime | Time slice (daily)     |
  | env_cloud_location     | string   | Region                 |
  | env_cloud_role         | string   | Resource (Service role)|
  | env_cloud_roleInstance | string   | Pod/instance           |
  | resourceId             | string   | ARM resource id        |
  | totalUpTimeSec         | real     | Up time seconds        |
  | totalTimeSec           | real     | Total seconds baseline |

- Column Explain:
  - env_time: align to Date via project-rename and bin with startofweek/month
  - resourceId/env_cloud_role: join key to billing/usage after lowercasing and replica normalization
  - totalUpTimeSec/totalTimeSec: compute QoS and SLA attainment

### ConnectivityQoS_Daily (signalrinsights.eastus2/SignalRBI)
- Represents: Daily connectivity QoS fact (service up/down baseline).
- Use/avoid: Same as OperationQoS_Daily; threshold often 0.995.
- Similar tables: OperationQoS_Daily.
- Common Filters: env_time windows; resourceId scope; deployment unit when needed.
- Columns

  | Column                 | Type     | Description |
  |------------------------|----------|-------------|
  | env_time               | datetime | Time slice  |
  | env_cloud_location     | string   | Region      |
  | env_cloud_deploymentUnit | string | Deployment SKU indicator (e.g., 'Dedicated', 'ServiceProcessUnit') |
  | env_cloud_role         | string   | Resource    |
  | resourceId             | string   | ARM id      |
  | totalUpTimeSec         | real     | Up time     |
  | totalTimeSec           | real     | Total time  |

- Column Explain:
  - env_cloud_deploymentUnit: used to split Share/Dedicated cohorts

### BillingUsage_Daily (signalrinsights.eastus2/SignalRBI)
- Represents: Daily usage/billing facts by ResourceId/SKU/Quantity/Region.
- When to use:
  - Revenue and quantity time-series by SKU, region, cohort
  - Active resource gating with QoS or connection facts
  - Completeness gating via region coverage
- When to avoid:
  - Counting unique resources without normalizing replicas
  - Joining without excluding SignalRTeamInternalSubscriptionIds
- Similar tables: Cached revenue KPI snapshots (use those for curated OKR dashboards).
- Common Filters (important):
  - Date windows; ResourceId has '/signalr/' or '/webpubsub/'
  - SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
  - SKU in ('Standard','Premium') for paid-only cohorts
- Columns

  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Date          | datetime | Usage date  |
  | ResourceId    | string   | ARM id      |
  | SubscriptionId| string   | Subscription owner |
  | SKU           | string   | Free/Standard/Premium/MessageCount |
  | Quantity      | real     | Units consumed |
  | Region        | string   | Azure region |

- Column Explain:
  - SKU: cohorting by price plan; exclude 'MessageCount' in many aggregation contexts
  - Quantity: multiply by per-SKU unit price to calculate revenue
  - Region: sentinel for completeness gates and regional splits

### MaxConnectionCount_Daily (signalrinsights.eastus2/SignalRBI)
- Represents: Daily max concurrent connections per resource.
- When to use:
  - HasConnection flag per day/week/month
  - LiveRatio classification (ActiveDays)
  - Activity cohorts by SKU (joined via BillingUsage_Daily)
- When to avoid:
  - Revenue or message volume—use BillingUsage_Daily/SumMessageCount_Daily
- Similar tables: AvgConnectionCountEP_Daily for average EP connections
- Common Filters (important):
  - Role has '/signalr/' or contains 'webpubsub'
  - SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
  - Align with BillingUsage_Daily on Date + normalized resource id
- Columns

  | Column            | Type     | Description |
  |-------------------|----------|-------------|
  | Date              | datetime | Day         |
  | Role              | string   | Resource path (acts as ResourceId) |
  | SubscriptionId    | string   | Subscription |
  | MaxConnectionCount| long/real| Max connections that day |
  | Region            | string   | Region (sometimes appears as Region1 in joins) |

- Column Explain:
  - Role: lower() and strip '/replicas/' before joins
  - MaxConnectionCount: basis for HasConnection and activity cohorts

### SumMessageCount_Daily (signalrinsights.eastus2/SignalRBI)
- Represents: Daily total messages per resource.
- Use:
  - Workload intensity; top subscriptions via message counts
- Columns

  | Column       | Type     | Description |
  |--------------|----------|-------------|
  | Date         | datetime | Day         |
  | Role         | string   | Resource id |
  | MessageCount | long     | Messages    |

### SubscriptionMappings (signalrinsights.eastus2/SignalRBI)
- Represents: Enrichment mapping subscription→customer/cohort metadata.
- Use:
  - CustomerType, SegmentName, CloudCustomerGuid, OfferName/Type, BillingType, TP/360 context
- Columns (observed)

  | Column            | Type   | Description |
  |-------------------|--------|-------------|
  | SubscriptionId    | string | Key for join |
  | CustomerType1     | string | CustomerType (used as CustomerType) |
  | CloudCustomerGuid | string | Customer id |
  | SegmentName       | string | Segment |
  | BillingType       | string | Billing context |
  | OfferType         | string | Offer type |
  | OfferName         | string | Offer name |
  | TPID/TPName       | string | Partner info |

### RPSettingLatest (signalrinsights.eastus2/SignalRBI)
- Represents: Latest RP settings per resource (Kind, ServiceMode, Extras).
- Use:
  - Feature cohorts (e.g., SocketIO, Serverless)
  - Aspire feature presence (Extras has 'isAspire')
- Columns

  | Column     | Type     | Description |
  |------------|----------|-------------|
  | ResourceId | string   | Join key    |
  | Kind       | string   | Resource kind ('SignalR','WebPubSub','SocketIO') |
  | ServiceMode| string   | 'Default','Serverless','ServerMode' |
  | Extras     | dynamic  | JSON extras (e.g., socketIO.serviceMode, isAspire) |
  | SKU1       | string   | SKU observed in joins |

### FeatureTrackV2_Daily / FeatureTrackV2_EU_Daily (signalrinsights.eastus2/SignalRBI)
- Represents: Feature use facts (RequestCount) per resource/feature/category; EU variant replicates EU ingestion.
- Use:
  - Feature adoption, errors signaled via features (e.g., Upstream_Exceptions)
- Columns

  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Date          | datetime | Day         |
  | ResourceId    | string   | ARM id      |
  | SubscriptionId| string   | Subscription|
  | Feature       | string   | Feature key |
  | Category      | string   | Category    |
  | RequestCount  | long     | Requests    |
  | Properties    | dynamic  | Additional info (project-away in many queries) |

### RuntimeRequestsGroups_Daily, RuntimeTransport_Daily, RuntimeTransport_EU_Daily
- Represents: Runtime request counts by category/metrics (and transport by framework/transport).
- Use:
  - Feature and transport usage over time; union EU and non-EU before summarize.

### ConnectionQoS_Daily (signalrinsights.eastus2/SignalRBI)
- Represents: Connection counts and QoS by endpoint (Server/Client).
- Columns

  | Column                 | Type     | Description |
  |------------------------|----------|-------------|
  | Date                   | datetime | Day         |
  | ResourceId             | string   | ARM id      |
  | Endpoint               | string   | 'Server'/'Client' |
  | TotalConnection        | long     | Total attempted |
  | SuccessConnection      | long     | Success count |
  | ServiceAbortedConnection | long   | Service-aborted |

### ErrorsRedis_Hourly, RuntimeExceptions_Hourly, RPExceptions_Hourly
- Represents: Error diagnostics per hour from runtime/redis/RP.
- Use:
  - Burst detection, cluster/pod/DeploymentId mapping, top error messages.
- Columns (observed)
  - ErrorsRedis_Hourly: DateHour, Cluster, ErrorType, ErrorCount, ResourceId, PodName
  - RuntimeExceptions_Hourly: Timestamp, Logger, ErrorType, ErrorMessage, ErrorCount, ResourceId, PodName, Cluster
  - RPExceptions_Hourly: Timestamp, ErrorType, ShortMessage, ServiceTypeName, ErrorCount, CorrelationRequestId

### WebTools_Raw (ddtelinsights)
- Represents: Developer tooling telemetry (VS/Web Tools).
- Columns

  | Column                       | Type     | Description |
  |------------------------------|----------|-------------|
  | AdvancedServerTimestampUtc   | datetime | Event time  |
  | EventName                    | string   | Event id    |
  | ExeVersion                   | string   | Client version |
  | Properties                   | dynamic  | Properties bag |
  | Measures                     | dynamic  | Measures bag |
  | MacAddressHash               | string   | Device id hash |
  | ActiveProjectId              | string   | Project id |

### ARM Requests (armprodgbl.eastus)
- Requests, HttpIncomingRequests; often combined via Unionizer helper.
- Columns

  | Column               | Type     | Description |
  |----------------------|----------|-------------|
  | TIMESTAMP            | datetime | Event time  |
  | targetResourceProvider| string  | Provider    |
  | targetResourceType   | string   | Type path   |
  | httpMethod           | string   | HTTP verb   |
  | targetUri            | string   | URI         |
  | subscriptionId       | string   | Sub id      |
  | SourceNamespace      | string   | Source      |

## Views (Reusable Layers)
No reusable views were defined in the provided content. Several helper functions are referenced (e.g., Unionizer(...), ResourceFlow_Weekly/Monthly, SubscriptionFlow_Weekly/Monthly, CustomerFlow_Weekly/Monthly, DailyResource, SignalRTeamInternalSubscriptionIds()); treat them as prebuilt functions available in the environment.

## Query Building Blocks (Copy-paste snippets)

### Time window templates
- Safe daily window with completeness gate (two sentinel regions):
  kusto
  let EndDate = toscalar(
    BillingUsage_Daily
    | where Date > ago(16d) and Region in ('australiaeast','westeurope')
    | summarize rc = dcount(Region) by Date
    | where rc >= 2
    | top 1 by Date desc
    | project Date
  );
  // Use [StartDate, EndDate]
  let StartDate = EndDate - 60d;
  <YourTable>
  | where Date between (StartDate .. EndDate)

- Weekly and monthly binning:
  kusto
  <YourTable>
  | where Date >= startofweek(now(), -8)
  | summarize <metric>=<agg>(<field>) by Week = startofweek(Date), <keys...>

  <YourTable>
  | where Date >= startofmonth(now(), -12)
  | summarize <metric>=<agg>(<field>) by Month = startofmonth(Date), <keys...>

- Rolling window anchored to latest available slice (QoS pattern):
  kusto
  let anchor = toscalar(OperationQoS_Daily | top 1 by env_time desc | project env_time);
  OperationQoS_Daily
  | where env_time > anchor - 7d
  | summarize Qos = iif(sum(totalTimeSec)==0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec)) by Date=anchor, Type='Rolling7'
  | union (
    OperationQoS_Daily
    | where env_time > anchor - 28d
    | summarize Qos = iif(sum(totalTimeSec)==0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec)) by Date=anchor, Type='Rolling28'
  )

### Join templates
- Enrich usage with subscription/customer cohorts:
  kusto
  BillingUsage_Daily
  | where Date between (ago(60d) .. now()-1d)
  | where ResourceId has 'microsoft.signalrservice/signalr'
  | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
  | join kind=leftouter SubscriptionMappings on SubscriptionId
  | summarize Quantity = sum(Quantity) by Date, SKU, CustomerType=CustomerType1, SegmentName

- Align resource keys across tables (normalize casing and replicas):
  kusto
  let usage = BillingUsage_Daily
    | extend Role = tolower(ResourceId)
    | project Date, Role, SubscriptionId, SKU, Quantity;
  let conn = MaxConnectionCount_Daily
    | extend Role = tolower(Role)
    | project Date, Role, MaxConnectionCount;
  usage
  | join kind=inner conn on Date, Role
  | summarize HasConnection = max(MaxConnectionCount) > 0 by Date, SubscriptionId, SKU

### De-dup patterns
- Latest partition row (rank then pick first):
  kusto
  ConvertCustomer_Weekly
  | order by Week asc, RunDay desc
  | extend Rank = row_number(1, prev(Week) != Week)
  | where Rank == 1

- Resource/day distinct for unique sets:
  kusto
  MaxConnectionCount_Daily
  | where Date >= startofweek(now(), -8)
  | extend Week = startofweek(Date)
  | distinct Week, Role, SubscriptionId

### Important filters and standardizations
- Exclude internal/test:
  kusto
  | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())

- API allowlist cohort:
  kusto
  let AllowedApis =
    ManageRPQosDaily
    | where Date > ago(30d)
    | where CustomerType in ('SignalR','') and ApiName !in ('UNCATEGORY','Internal-ACIS')
    | where ApiName !in ('INVALID','GetResource','OperationList','OperationResult','UpdateSubscription')
    | where ApiName !contains 'acs' and !contains 'acis'
    | distinct ApiName;
  ManageRPQosDaily
  | join kind=inner AllowedApis on ApiName
  | summarize QoS = 1.0*sumif(Count, Result in ('Success','Timeout','CustomerError'))/sum(Count) by Date, Region

### ID parsing/derivation
- SubscriptionId from ResourceId:
  kusto
  | extend SubscriptionId = tostring(split(ResourceId, '/')[2])

- Primary resource from replicas:
  kusto
  | extend PrimaryResource = iif(ResourceId has '/replicas/', substring(ResourceId, 0, indexof(ResourceId, '/replicas/')), ResourceId)

- ARM action cohort from URI:
  kusto
  | extend ResourceId = substring(targetUri, 33, indexof(targetUri, '?') - 33)
  | extend action = iif(httpMethod == 'PUT', 'AddEventGrid', 'DeleteEventGrid')

### Sharded union (EU/non-EU)
- FeatureTrack union with EU shard:
  kusto
  FeatureTrackV2_Daily
  | union FeatureTrackV2_EU_Daily
  | where Date > startofweek(now()) - 56d
  | project-away Properties
  | extend Date = startofday(Date)
  | summarize RequestCount = sum(RequestCount) by Date, Feature, ResourceId, SubscriptionId, Category

## Example Queries (with explanations)

1) Operation QoS daily and SLA attainment (SignalR)
- Description: Computes per-day QoS and SLA attainment (threshold 0.999) by region and overall for SignalR resources over last 43 days. Raw per-resource QoS is summarized to region and an “Overall” aggregate.
- Query:
  kusto
  let raw = OperationQoS_Daily
  | where env_time > ago(43d) and resourceId has '/signalr/'
  | summarize Qos = iif(sum(totalTimeSec) == 0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec)), UpTime = sum(totalUpTimeSec), TotalTime = sum(totalTimeSec) by Date = env_time, Region = env_cloud_location, ResourceId = env_cloud_role;
  raw
  | summarize TotalOperation = sum(TotalTime), Qos = iif(sum(TotalTime) == 0, 1.0, 1.0*sum(UpTime)/sum(TotalTime)), SlaAttainment = 1.0 * dcountif(ResourceId, Qos >=0.999, 4)/dcount(ResourceId, 4) by Date, Region
  | union ( raw
  | summarize TotalOperation = sum(TotalTime), Qos = iif(sum(TotalTime) == 0, 1.0, 1.0*sum(UpTime)/sum(TotalTime)), SlaAttainment = 1.0 * dcountif(ResourceId, Qos >=0.999, 4)/dcount(ResourceId, 4) by Date, Region = 'Overall')

2) Connectivity QoS rolling windows (SignalR)
- Description: Anchors to latest env_time and recomputes 7- and 28-day rolling QoS. Useful when the last day is partially ingested; the anchor ensures consistent windows.
- Query:
  kusto
  let dateFilter = ConnectivityQoS_Daily
  | top 1 by env_time desc
  | project env_time, fakeKey = 1;
  ConnectivityQoS_Daily
  | where env_time > ago(10d) and resourceId contains 'microsoft.signalrservice/signalr'
  | extend fakeKey = 1
  | join kind = inner dateFilter on fakeKey
  | where env_time > env_time1 - 7d
  | summarize Qos = iif(sum(totalTimeSec) == 0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec)) by Date=env_time1, Type = 'Rolling7'
  | union (
  ConnectivityQoS_Daily
  | where env_time > ago(30d) and resourceId contains 'microsoft.signalrservice/signalr'
  | extend fakeKey = 1
  | join kind = inner dateFilter on fakeKey
  | where env_time > env_time1 - 28d
  | summarize Qos = iif(sum(totalTimeSec) == 0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec)) by Date=env_time1, Type = 'Rolling28')

3) Weekly resource activity and live ratio (SignalR)
- Description: Joins max connections with billing to classify resources by HasConnection and LiveRatio per week, excluding internal subscriptions. Adapt time range/SKU gates to your need.
- Query:
  kusto
  MaxConnectionCount_Daily
      | where Date >= startofweek(now(), -8) and SubscriptionId !in (SignalRTeamInternalSubscriptionIds()) and Role has '/signalr/'
      | join kind = inner BillingUsage_Daily on $left.Role == $right.ResourceId, Date
      | summarize Conn = max(MaxConnectionCount), SKU = max(SKU), Region = max(Region1), ActiveDays = dcount(Date) by Week=startofweek(Date), ResourceId
      | project Week, ResourceId, Category = 'Total', Region, SKU, HasConnection = Conn > 0, LiveRatio = case(ActiveDays < 3, 'Swift', 'Occasional')
      | summarize ResourceCnt = dcount(ResourceId, 3) by Week, Category, Region, SKU, HasConnection, LiveRatio

4) Revenue by SKU with parameterized prices (SignalR)
- Description: Calculates daily revenue by SKU and CustomerType using parameterized unit prices and excluding internal subscriptions. Change the time range, SKUs, or cohort fields as needed.
- Query:
  kusto
  let StandardUnitPrice = 1.61;
  let PremiumUnitPrice  = 2.0;
  let EndDate = toscalar(BillingUsage_Daily | where Date > ago(10d) and Region in ('australiaeast', 'westeurope') 
  | summarize counter = dcount(Region) by Date | where counter >= 2 | top 1 by Date desc | project Date);
  BillingUsage_Daily
  | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds) and Date >= ago(60d) and ResourceId has '/signalr/' and Date <= EndDate
  | extend Revenue = case(SKU == 'Free', 0.0, SKU == 'Standard', StandardUnitPrice, SKU == 'Premium', PremiumUnitPrice, 1.0)*Quantity
  | join kind = leftouter SubscriptionMappings on SubscriptionId
  | summarize Total = sum(Quantity), Revenue = sum(Revenue) by Date, SKU, CustomerType

5) Feature usage with EU sharded union (SignalR)
- Description: Unions EU and non-EU feature tracking, aligns dates, joins billing to ensure real resources, then summarizes request counts per week/feature. Adapt Feature filters and SKU gating.
- Query:
  kusto
  FeatureTrackV2_Daily 
      | union FeatureTrackV2_EU_Daily
      | where Date > startofweek(now()) - 56d 
      | project-away Properties
      | extend Date = startofday(Date), Category = case(Feature in ('BlazorServerSide', 'Samples'), Feature, Category endswith 'Ping', substring(Category, 8, indexof(Category, 'Ping') - 8), Category)
      | where ResourceId has 'microsoft.signalrservice/signalr' and SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
      | join kind = inner (BillingUsage_Daily | where SKU !in ('MessageCount', 'MessageCountPremium')) on Date, ResourceId
      | summarize RequestCount = sum(RequestCount), SKU = max(SKU) by Week = startofweek(Date), Feature, ResourceId, SubscriptionId, Category

6) Developer tools SignalR detection ratio (ddtelinsights)
- Description: Computes a ratio of projects where SignalR was detected vs. total publish-project events. Aligns by day. Modify EventName/filters or version thresholds as needed.
- Query:
  kusto
  WebTools_Raw
  | where AdvancedServerTimestampUtc >= ago(30d)
  | where EventName in ('vs/managedpublish/publish-project', 'vs/webtools/managedpublish/publish-project')
  | extend IsVs22 = ExeVersion startswith '17.'
  | extend IsNetCore = iif(IsVs22, tobool(Properties['vs.webtools.managedpublish.isnetcoreproject']), tobool(Properties['vs.managedpublish.isnetcoreproject'])), 
  ProfileHandler = iif(IsVs22, tostring(Properties['vs.webtools.managedpublish.profilehandlertype']), tostring(Properties['vs.managedpublish.profilehandlertype']))
  | where IsNetCore
  | extend ExeMajorVersion = todecimal(strcat(split(ExeVersion, '.')[0], '.', split(ExeVersion, '.')[1]))
  | where ExeMajorVersion >= 16.1
  | extend Date = startofday(AdvancedServerTimestampUtc)
  | summarize PublishProjectDevCount = dcount(MacAddressHash) by Date
  | join kind=leftouter (WebTools_Raw
  | where AdvancedServerTimestampUtc >= ago(30d)
  | where Properties contains 'Microsoft.SignalRService/SignalR' or (EventName == 'vs/webtools/servicedependencies/state' and Measures contains 'signalr' and Properties['vs.webtools.servicedependencies.profiletype'] == 'remote')
  | extend ExeMajorVersion = todecimal(strcat(split(ExeVersion, '.')[0], '.', split(ExeVersion, '.')[1]))
  | where ExeMajorVersion >= 16.1
  | extend Date = startofday(AdvancedServerTimestampUtc)
  | summarize SignalRDetectedDevCount = dcount(MacAddressHash) by Date) on $left.Date == $right.Date
  | extend SignalRRatio = todecimal(SignalRDetectedDevCount)/PublishProjectDevCount
  | project Date, PublishProjectDevCount, SignalRDetectedDevCount, SignalRRatio

7) Connection QoS percentiles by cohorts
- Description: Computes per-day ServiceQos for all resources, then tdigest percentiles and averages; variants shown for Standard SKU and deployment unit cohorts. Adapt joins/thresholds as needed.
- Query:
  kusto
  // Overall
  ConnectionQoS_Daily
  | where Date > ago(30d)
  | summarize ServiceQos = 1- 1.0*sum(ServiceAbortedConnection)/sum(TotalConnection) by Date, ResourceId
  | summarize tdigest_Qos = tdigest(ServiceQos), AvgQos = avg(ServiceQos) by Date
  | project Date, PRQos = todecimal(percentile_tdigest(tdigest_Qos, 10)), AvgQos
  //
  // Standard SKU
  ; ConnectionQoS_Daily
  | where Date > ago(30d)
  | join kind = inner (BillingUsage_Daily | where SKU == 'Standard') on Date, ResourceId
  | summarize ServiceQos = 1- 1.0*sum(ServiceAbortedConnection)/sum(TotalConnection) by Date, ResourceId
  | summarize tdigest_Qos = tdigest(ServiceQos), AvgQos_Standard = avg(ServiceQos) by Date
  | project Date, PRQos_Standard = todecimal(percentile_tdigest(tdigest_Qos, 15)), AvgQos_Standard
  //
  // Share vs. Dedicated (deployment unit)
  ; ConnectionQoS_Daily
  | where Date > ago(30d)
  | join kind = inner (ConnectivityQoS_Daily | where env_cloud_deploymentUnit == 'Dedicated'
  | project Date = env_time, ResourceId = resourceId) on Date, ResourceId
  | summarize ServiceQos = 1- 1.0*sum(ServiceAbortedConnection)/sum(TotalConnection) by Date, ResourceId
  | summarize tdigest_Qos = tdigest(ServiceQos), AvgQos = avg(ServiceQos) by Date
  | project Date, PRQos_Dedicated = todecimal(percentile_tdigest(tdigest_Qos, 15)), AvgQos_Dedicated = AvgQos

8) “AI keyword” subscription cohort with rolling month comparisons
- Description: Tracks subscriptions whose resource ids include AI-related keywords, in 28-day rolling windows aligned to latest consistent day across two sentinel regions. Produces month-stamped points for latest and prior window and historical months with goals.
- Query:
  kusto
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

9) ARM requests cohort for Event Grid filters (ARM)
- Description: Cross-source ARM telemetry for PUT/DELETE against SIGNALR/EVENTGRIDFILTERS excluding known internal subscriptions; extracts ResourceId, action, and location. Adjust provider/type as needed.
- Query:
  kusto
  Unionizer('Requests', 'HttpIncomingRequests')
  | where TIMESTAMP > ago (30d) and targetResourceProvider == 'MICROSOFT.SIGNALRSERVICE' and httpMethod in ('PUT', 'DELETE') and targetResourceType == 'SIGNALR/EVENTGRIDFILTERS'
  | where subscriptionId !in ('9caf2a1e-9c49-49b6-89a2-56bdec7e3f97', '2085065b-00f8-4cba-9675-ba15f4d4ab66', '685ba005-af8d-4b04-8f16-a7bf38b2eb5a', '1c5b82ee-9294-4568-b0c0-b9c523bc0d86')
  | extend ResourceId = substring(targetUri, 33, indexof(targetUri, '?') - 33),
           action = iif( httpMethod == 'PUT', 'AddEventGrid', 'DeleteEventGrid'),
           Date = startofday(TIMESTAMP),
           Location = trim_end('RPF', trim_start('csm', SourceNamespace))
  | distinct Date, ResourceId, subscriptionId, action, Location

10) Socket.IO serverless share (Web PubSub)
- Description: Finds Web PubSub resources with Kind=='SocketIO', groups weekly, and calculates the serverless share over all SocketIO resources, split by SKU and team subs. Tune timeframe or IsTeamSubs gating as needed.
- Query:
  kusto
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

## Reasoning Notes (only if uncertain)
- Timezone: Data likely UTC; not explicitly stated. We adopt UTC and recommend excluding “today” or gating via EndDate when accuracy matters.
- Internal subscription function: SignalRTeamInternalSubscriptionIds() appears as both a function call and a name; we adopt the callable form and, where present, set membership semantics (both are shown in queries).
- Role vs. ResourceId: MaxConnectionCount_Daily and similar use Role as the resource key; we normalize Role as ResourceId (tolower, strip replicas) before joining with BillingUsage_Daily.ResourceId.
- Region field ambiguity: Some joins reference Region1 after joins. We coalesce Region fields post-join; exact column naming can vary by upstream pipeline.
- ManageRP QoS success cohorts: SignalR often includes Timeout/CustomerError as acceptable; WebPubSub examples use Result == 'Success'. We keep both patterns and recommend picking the stricter or broader set per scenario.
- Revenue unit prices: Numbers appear (1.61, 2.0). We parameterize these in templates (<StandardUnitPrice>, <PremiumUnitPrice>) to avoid hardcoding and simplify scenario changes.
- EU sharding: FeatureTrackV2 and RuntimeTransport have EU shards; the standard is union then normalize and summarize. If additional shards exist, extend the union with the same schema.
- Completeness gates: Two-region and ≥38-region gates appear; adopt the stricter gate for Web PubSub when working at global scope and the lighter gate for narrow-scope experiments.
- Snapshot vs. facts: Cached_* tables are curated aggregates; use them for dashboards and OKR overlays; prefer fact tables for drill-downs and ad-hoc joins with other facts.