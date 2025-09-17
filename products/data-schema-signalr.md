# SignalR - Product and Data Overview Template

## 1. Product Overview

SignalR is a real-time messaging service in Azure, supporting both SignalR and Web PubSub workloads. This onboarding covers the PowerBI/ADX queries and datasets for operational QoS, connectivity, service usage, management, billing, retention, customer and subscription analytics, and feature tracking. The main data source is the `signalrinsights.eastus2` cluster and `SignalRBI` database.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**: SignalR
- **Product Nick Names**:  
  > **[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations.
- **Kusto Cluster**: signalrinsights.eastus2
- **Kusto Database**: SignalRBI
- **Access Control**:  
  > **[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed **groups/users** here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

## 3. Table Schemas in Azure Data Explorer

### OperationQoS_Daily

| Column                | Type     |
|-----------------------|----------|
| env_name              | string   |
| env_time              | datetime |
| resourceId            | string   |
| env_cloud_role        | string   |
| env_cloud_roleInstance| string   |
| env_cloud_environment | string   |
| env_cloud_location    | string   |
| env_cloud_deploymentUnit | string|
| totalUpTimeSec        | long     |
| totalTimeSec          | long     |

### ConnectivityQoS_Daily

| Column                | Type     |
|-----------------------|----------|
| env_name              | string   |
| env_time              | datetime |
| resourceId            | string   |
| env_cloud_role        | string   |
| env_cloud_roleInstance| string   |
| env_cloud_environment | string   |
| env_cloud_location    | string   |
| env_cloud_deploymentUnit | string|
| totalUpTimeSec        | long     |
| totalTimeSec          | long     |

### MaxConnectionCount_Daily

| Column            | Type     |
|-------------------|----------|
| Date              | datetime |
| Role              | string   |
| SubscriptionId    | string   |
| CustomerType      | string   |
| Region            | string   |
| MaxConnectionCount| long     |

### RPSettingLatest

| Column                | Type     |
|-----------------------|----------|
| ResourceId            | string   |
| Region                | string   |
| SKU                   | string   |
| Kind                  | string   |
| State                 | string   |
| ServiceMode           | string   |
| IsUpstreamSet         | bool     |
| IsEventHandlerSet     | bool     |
| EnableTlsClientCert   | bool     |
| IsPrivateEndpointSet  | bool     |
| EnablePublicNetworkAccess | bool |
| DisableLocalAuth      | bool     |
| DisableAadAuth        | bool     |
| IsServerlessTimeoutSet| bool     |
| AllowAnonymousConnect | bool     |
| EnableRegionEndpoint  | bool     |
| ResourceStopped       | bool     |
| EnableLiveTrace       | bool     |
| EnableResourceLog     | bool     |
| LastUpdated           | datetime |
| Extras                | string   |

### SubscriptionMappings

| Column            | Type     |
|-------------------|----------|
| P360_ID           | string   |
| CloudCustomerGuid | string   |
| SubscriptionId    | string   |
| CustomerType      | string   |
| CustomerName      | string   |
| SegmentName       | string   |
| OfferType         | string   |
| OfferName         | string   |
| BillingType       | string   |
| WorkloadType      | string   |
| S500              | string   |

### SumMessageCount_Daily

| Column            | Type     |
|-------------------|----------|
| Date              | datetime |
| Role              | string   |
| Region            | string   |
| SubscriptionId    | string   |
| CustomerType      | string   |
| MessageCount      | long     |

### AvgConnectionCountEP_Daily

| Column            | Type     |
|-------------------|----------|
| Date              | datetime |
| Role              | string   |
| SubscriptionId    | string   |
| CustomerType      | string   |
| Region            | string   |
| Endpoint          | string   |
| AvgConnectionCount| long     |

### ManageRPQosDaily

| Column            | Type     |
|-------------------|----------|
| Date              | datetime |
| ApiName           | string   |
| SubscriptionId    | string   |
| CustomerType      | string   |
| Region            | string   |
| Result            | string   |
| Count             | long     |

### BillingUsage_Daily

| Column            | Type     |
|-------------------|----------|
| Date              | datetime |
| Region            | string   |
| SubscriptionId    | string   |
| ResourceId        | string   |
| SKU               | string   |
| Quantity          | real     |

### RuntimeRequestsGroups_Daily

| Column            | Type     |
|-------------------|----------|
| Date              | datetime |
| Category          | string   |
| Metrics           | string   |
| ResourceCount     | long     |
| RequestCount      | long     |

### RuntimeTransport_Daily / RuntimeTransport_EU_Daily

| Column            | Type     |
|-------------------|----------|
| Date              | datetime |
| Feature           | string   |
| Transport         | string   |
| Framework         | string   |
| ResourceId        | string   |
| SubscriptionId    | string   |
| RequestCount      | long     |

### KPIv2019

| Column            | Type     |
|-------------------|----------|
| Date              | datetime |
| SubscriptionCount | long     |
| ResourceCount     | long     |

### ChurnCustomers_Monthly

| Column            | Type     |
|-------------------|----------|
| Month             | datetime |
| ServiceType       | string   |
| Total             | long     |
| Churn             | long     |
| Standard          | long     |
| StandardChurn     | long     |
| RunDay            | datetime |

### ConvertCustomer_Weekly

| Column            | Type     |
|-------------------|----------|
| Week              | datetime |
| ServiceType       | string   |
| FreeToStandard    | long     |
| TotalCustomers    | long     |
| StandardCustomers | long     |
| RunDay            | datetime |
| FreeToPaid        | long     |
| StandardToPremium | long     |
| FreeToPremium     | long     |
| PremiumCustomers  | long     |

### DeleteSurvey

| Column            | Type     |
|-------------------|----------|
| TIMESTAMP         | datetime |
| Deployment        | string   |
| resourceId        | string   |
| reason            | string   |
| feedback          | string   |
| objectId          | string   |
| sessionId         | string   |

### CustomerRetentionSnapshot

| Column            | Type     |
|-------------------|----------|
| C360_ID           | string   |
| StartDate         | datetime |
| EndDate           | datetime |

### SubscriptionRetentionSnapshot

| Column            | Type     |
|-------------------|----------|
| SubscriptionId    | string   |
| StartDate         | datetime |
| EndDate           | datetime |

### ResourceRetentionSnapshot

| Column            | Type     |
|-------------------|----------|
| ResourceId        | string   |
| StartDate         | datetime |
| EndDate           | datetime |

### Cached_ResourceFlow_Snapshot

| Column            | Type     |
|-------------------|----------|
| Category          | string   |
| Region            | string   |
| SKU               | string   |
| HasConnection     | bool     |
| LiveRatio         | string   |
| ResourceCnt       | long     |
| Date              | datetime |
| ServiceType       | string   |
| Partition         | string   |

### Cached_SubsTotalWeekly_Snapshot

| Column            | Type     |
|-------------------|----------|
| Week              | datetime |
| ServiceType       | string   |
| SubscriptionId    | string   |
| Region            | string   |
| SKU               | string   |
| HasConnection     | bool     |
| LiveRatio         | string   |

### Cached_SubsTotalMonthly_Snapshot

| Column            | Type     |
|-------------------|----------|
| Month             | datetime |
| ServiceType       | string   |
| SubscriptionId    | string   |
| Region            | string   |
| SKU               | string   |
| HasConnection     | bool     |
| LiveRatio         | string   |

### Cached_CustomerFlow_Snapshot

| Column            | Type     |
|-------------------|----------|
| Category          | string   |
| Region            | string   |
| SKU               | string   |
| HasConnection     | bool     |
| LiveRatio         | string   |
| CustomerType      | string   |
| SegmentionType    | string   |
| CustomerCnt       | long     |
| Date              | datetime |
| ServiceType       | string   |
| Partition         | string   |

### Cached_Asrs_TopCustomersWoW_v2_Snapshot

| Column                    | Type     |
|---------------------------|----------|
| P360_ID                   | string   |
| P360_CustomerDisplayName  | string   |
| SKU                       | string   |
| CustomerType              | string   |
| BillingType               | string   |
| Category                  | string   |
| CurrentValue              | real     |
| P360Url                   | string   |
| LastDay                   | datetime |
| UsageType                 | string   |
| CurrentValue1             | real     |
| PrevValue                 | real     |
| W3Value                   | real     |
| DeltaValue                | real     |
| Rank                      | long     |
| W1Rank                    | long     |
| W3Rank                    | long     |

### FeatureTrackV2_Daily / FeatureTrackV2_EU_Daily / FeatureTrack_AutoScale_Daily / FeatureTrack_Daily

| Column            | Type     |
|-------------------|----------|
| Date              | datetime |
| Feature           | string   |
| Category          | string   |
| ResourceId        | string   |
| SubscriptionId    | string   |
| Properties        | string   |
| RequestCount      | long     |

### ManageResourceTags

| Column            | Type     |
|-------------------|----------|
| Date              | datetime |
| SubscriptionId    | string   |
| ResourceId        | string   |
| RequestName       | string   |
| Tags              | string   |
| Count             | long     |

### AwpsRuntimeRequestsGroups_Daily

| Column            | Type     |
|-------------------|----------|
| Date              | datetime |
| Category          | string   |
| Metrics           | string   |
| ResourceCount     | long     |
| RequestCount      | long     |

### KPI_AWPS / KPI_SocketIO

| Column            | Type     |
|-------------------|----------|
| Date              | datetime |
| SubscriptionCount | long     |
| ResourceCount     | long     |

### OKRv2021 / OKRv2021_AWPS / OKRv2021_SocketIO

| Column            | Type     |
|-------------------|----------|
| Date              | datetime |
| Category          | string   |
| Value             | real     |

### AwpsRetention_SubscriptionSnapshot

| Column            | Type     |
|-------------------|----------|
| SubscriptionId    | string   |
| StartDate         | datetime |
| EndDate           | datetime |

### AwpsRetention_CustomerSnapshot

| Column            | Type     |
|-------------------|----------|
| C360_ID           | string   |
| StartDate         | datetime |
| EndDate           | datetime |

### AwpsRetention_ResourceSnapshot

| Column            | Type     |
|-------------------|----------|
| ResourceId        | string   |
| StartDate         | datetime |
| EndDate           | datetime |

---

# SignalR Kusto Query Playbook

## Overview

**Product Name:** SignalR  
**Summary:**  
This dataset contains PowerBI/ADX queries for SignalR and Web PubSub, covering operational QoS, connectivity, service usage, management, billing, retention, customer and subscription analytics, and feature tracking. The main data source is the `signalrinsights.eastus2` cluster and `SignalRBI` database.

**Primary Cluster:** `signalrinsights.eastus2`  
**Primary Database:** `SignalRBI`  

---

## Conventions & Assumptions

### Time Semantics

- **Timestamp Columns Observed:**  
  - `env_time` (OperationQoS_Daily, ConnectivityQoS_Daily)
  - `Date` (most daily tables)
  - `Month`, `Week` (monthly/weekly tables)
  - `StartDate`, `EndDate` (retention/snapshot tables)
  - `TIMESTAMP` (DeleteSurvey)
- **Canonical Time Column:**  
  - Use `Date` for daily aggregations.  
  - Alias other columns to `Date` via `project-rename` as needed.
- **Typical Windows:**  
  - `ago(30d)`, `ago(43d)` for recent data.
  - Monthly/weekly bins: use `bin(Date, 1d)`, `bin(Date, 7d)`, `bin(Date, 30d)` as appropriate.
- **Timezone:**  
  - Not explicitly stated. **Assume UTC** unless otherwise specified.

### Freshness & Completeness Gates

- **Ingestion Cadence:**  
  - Daily tables are used; current day may be incomplete.
- **Completeness Gate Pattern:**  
  - Use previous full day/week/month for reporting.  
  - For multi-region/sharded tables, recommend:  
    ```kusto
    let last_complete_day = toscalar(
      Table
      | summarize min_row_count = min(row_count()) by Date
      | where min_row_count > threshold
      | summarize max(Date)
    );
    Table | where Date == last_complete_day
    ```
  - If unknown, **avoid using current day**.

### Joins & Alignment

- **Frequent Keys:**  
  - `ResourceId`, `SubscriptionId`, `Region`, `CustomerType`, `P360_ID`, `C360_ID`
- **Typical Join Kinds:**  
  - `inner`, `innerunique`, `leftouter`
- **Post-Join Hygiene:**  
  - Use `project-rename` to align key names.
  - Use `coalesce()` for fallback values.
  - Drop unused columns with `project-away`.

### Filters & Idioms

- **Common Predicates:**  
  - `has`, `contains`, `in` (case-sensitive by default)
- **Cohort Construction:**  
  - Build allowlist/denylist via facts, then `join kind=inner` to filter.
- **Default Exclusions:**  
  - Exclude test/internal data using resource naming patterns or environment filters.

### Cross-Cluster/DB & Sharding

- **Source Qualification:**  
  - Use `cluster('signalrinsights.eastus2').database('SignalRBI').TableName` for explicit cross-cluster queries.
- **Sharded Tables:**  
  - For EU/region shards (e.g., `RuntimeTransport_Daily` vs. `RuntimeTransport_EU_Daily`):  
    ```kusto
    union RuntimeTransport_Daily, RuntimeTransport_EU_Daily
    | project-rename Date = Date, Region = Region, ...
    | summarize ...
    ```
  - Normalize keys/time before summarizing.

### Table Classes

- **Fact Tables:**  
  - Daily event counts, e.g., `SumMessageCount_Daily`, `MaxConnectionCount_Daily`
- **Snapshot Tables:**  
  - Latest state, e.g., `RPSettingLatest`, retention snapshots
- **Pre-aggregated Tables:**  
  - KPIs, cached flows, e.g., `KPIv2019`, `Cached_ResourceFlow_Snapshot`
- **Usage Guidance:**  
  - Use fact tables for time series/event analysis.
  - Use snapshot tables for current state.
  - Use pre-aggregated tables for reporting/KPIs; avoid for granular analysis.

---

## Entity & Counting Rules (Core Definitions)

### Entity Model

- **Resource:**  
  - Key: `ResourceId`
- **Subscription:**  
  - Key: `SubscriptionId`
- **Customer:**  
  - Key: `P360_ID`, `C360_ID`, `CloudCustomerGuid`
- **Grouping Levels:**  
  - By `Region`, `CustomerType`, `SKU`, `ServiceType`

### Business Definitions

- **QoS (Quality of Service):**  
  - Calculated as `sum(totalUpTimeSec) / sum(totalTimeSec)`; fallback to `1.0` if denominator is zero.
- **SLA Attainment:**  
  - Fraction of resources with QoS above threshold (e.g., `>=0.999` or `>=0.995`).
- **Churn/Retention:**  
  - Churn: customers/resources lost in a period.
  - Retention: tracked via snapshot tables (`StartDate`, `EndDate`).

---

## Canonical Tables

(See section 3 above for detailed schemas and usage notes.)

---

## Views (Reusable Layers)

*No explicit views defined in input. Build reusable layers as needed using `let` statements in queries.*

---

## Query Building Blocks (Copy-paste snippets, contains snippets and description)

### Time Window Template

```kusto
let startDate = datetime(2024-05-01);
let endDate = datetime(2024-05-31);
Table
| where Date >= startDate and Date < endDate
```
Or for rolling window:
```kusto
Table
| where Date > ago(30d)
```

### Join Template

```kusto
TableA
| join kind=inner (
    TableB
    | project SubscriptionId, CustomerType
) on SubscriptionId
```

### De-dup Pattern

```kusto
Table
| summarize arg_max(Date, *) by ResourceId
```

### Important Filters

```kusto
| where resourceId has '/signalr/'
| where Region in ('eastus', 'westus')
| where CustomerType != 'Internal'
```

### ID Parsing/Derivation

```kusto
| extend SubscriptionId = extract(@"subscriptions/([^/]+)", 1, resourceId)
```

### Sharded Union

```kusto
union RuntimeTransport_Daily, RuntimeTransport_EU_Daily
| project-rename Date = Date, Region = Region, ...
| summarize RequestCount = sum(RequestCount) by Date, Region, Transport
```

---

## Example Queries (with explanations)

### 1. QoS Daily Calculation

```kusto
OperationQoS_Daily
| where env_time > ago(43d) and resourceId has '/signalr/'
| summarize Qos = iif(sum(totalTimeSec) == 0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec)), UpTime = sum(totalUpTimeSec), TotalTime = sum(totalTimeSec) by Date = env_time, Region = env_cloud_location, ResourceId = env_cloud_role
```
**Description:**  
Calculates daily QoS, uptime, and total time for SignalR resources over the last 43 days, grouped by date, region, and resource. Adapt by changing the time window or resource filter.

---

### 2. SLA Attainment Summary

```kusto
OperationQoS_Daily
| where env_time > ago(43d) and resourceId has '/signalr/'
| summarize Qos = iif(sum(totalTimeSec) == 0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec)), UpTime = sum(totalUpTimeSec), TotalTime = sum(totalTimeSec) by Date = env_time, Region = env_cloud_location, ResourceId = env_cloud_role
| summarize TotalOperation = sum(TotalTime), Qos = iif(sum(TotalTime) == 0, 1.0, 1.0*sum(UpTime)/sum(TotalTime)), SlaAttainment = 1.0 * dcountif(ResourceId, Qos >=0.999, 4)/dcount(ResourceId, 4) by Date, Region
```
**Description:**  
Aggregates QoS and calculates SLA attainment per day and region. Use for reporting compliance.

---

### 3. Connectivity QoS Calculation

```kusto
ConnectivityQoS_Daily
| where env_time > ago(43d) and resourceId has '/signalr/'
| summarize Qos = iif(sum(totalTimeSec) == 0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec)), UpTime = sum(totalUpTimeSec), TotalTime = sum(totalTimeSec) by Date = env_time, Region = env_cloud_location, ResourceId = env_cloud_role
```
**Description:**  
Similar to operational QoS, but focused on connectivity metrics.

---

### 4. Max Connection Count by Subscription

```kusto
MaxConnectionCount_Daily
| where Date > ago(30d)
| summarize MaxConn = max(MaxConnectionCount) by SubscriptionId, Region
```
**Description:**  
Finds the peak connection count per subscription and region in the last 30 days.

---

### 5. Message Count Summary

```kusto
SumMessageCount_Daily
| where Date > ago(30d)
| summarize TotalMessages = sum(MessageCount) by SubscriptionId, Region
```
**Description:**  
Summarizes total message volume per subscription and region.

---

### 6. Resource Retention Snapshot

```kusto
ResourceRetentionSnapshot
| where EndDate > ago(30d)
| summarize ResourceCount = dcount(ResourceId) by bin(EndDate, 1d)
```
**Description:**  
Counts retained resources per day over the past 30 days.

---

### 7. Sharded Transport Usage

```kusto
union RuntimeTransport_Daily, RuntimeTransport_EU_Daily
| where Date > ago(30d)
| summarize TotalRequests = sum(RequestCount) by Date, Transport, Region
```
**Description:**  
Combines transport usage across regions, normalizes columns, and aggregates request counts.

---

## Reasoning Notes

- **Timezone is not specified**; UTC is assumed for all time columns.
- **Freshness gates** are not explicit; recommend using previous full day/week/month for reporting.
- **Entity keys** inferred from table schemas and query usage.
- **No explicit views**; reusable layers should be built via `let` blocks as needed.

---

**End of Playbook**