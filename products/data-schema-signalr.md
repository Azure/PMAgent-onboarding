# Azure SignalR Service / Azure Web PubSub – Product and Data Overview

## 1. Product Overview

Azure SignalR Service and Azure Web PubSub Service are fully managed services for building real-time web applications. They support WebSocket and other protocols to enable low-latency, high-frequency communication between clients and servers.

These two services share the same backend infrastructure and telemetry data in Azure Data Explorer.

### Key Features

- **Real-time Messaging**: Facilitates instant communication between servers and clients.
- **High Scalability**: Automatically scales to handle millions of concurrent connections.
- **Integration**: Seamlessly integrates with Azure Functions and other Azure services.
- **Service Modes**: Supports multiple service modes, including Default, Serverless, and Classic.

## 2. Azure Resource Structure

Each instance is uniquely identified by a `ResourceId`:

- **SignalR**:  
  `/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.SignalRService/SignalR/{resourceName}`

- **Web PubSub**:  
  `/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.SignalRService/WebPubSub/{resourceName}`

> Web PubSub includes two subtypes: the standard **Web PubSub** (commonly used by most users) and **Web PubSub for Socket.IO** (typically referred to as Socket.IO or SocketIO).
Socket.IO further supports two service modes: the default mode (more commonly used) and the serverless mode. Each resource can belong to only one subtype and one service mode, and this classification cannot be inferred from the `ResourceId` pattern alone. To determine the subtype and service mode, you must join with the `RPSettingLatest` table.

> A single `SubscriptionId` may contain multiple resources.  
> Multiple subscriptions can belong to the same customer, identified by a shared `CloudCustomerGuid`.
> When aggregating at the customer level, always group by `CloudCustomerGuid`. For subscription-level aggregation, use `SubscriptionId`, and for resource-level details, use `ResourceId`.

## 3. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**: AzureSignalRService
- **Kusto Cluster**: `https://signalrinsights.eastus2.kusto.windows.net`
- **Kusto Database**: `SignalRBI`
- **Primary Metrics**: Connection count, message count, and billed units are key indicators. While traffic metrics reflect usage, billed units represent fixed costs that apply even when a resource is idle. Billing typically combines base unit charges with additional message-based costs.

## 4. Table Schemas in Azure Data Explorer

### 4.1 `BillingUsage_Daily`

The `BillingUsage_Daily` table contains **daily billing summary data** at the granularity of **one row per (ResourceId, SKU, Date)**.  
Key characteristics:

- **Time Scope**: Data is recorded and finalized **after the end of each UTC day**.  
  - ⚠️ This means **no data is available for the current UTC day**.
- **Usage Fields**: The `Quantity` field represents billed units per SKU per day, reflecting resource usage and potential fixed charges.
- **Aggregation**: Because of daily granularity, this table can be used to infer resource or subscription **existence windows**, such as:
  - First seen date: `min(Date)` per `ResourceId` or `SubscriptionId`
  - Last seen date: `max(Date)` per `ResourceId` or `SubscriptionId`

| Column          | Type     | Description                         |
|-----------------|----------|-------------------------------------|
| Date            | datetime | Usage date                          |
| Region          | string   | Azure region                        |
| SubscriptionId  | string   | Azure subscription ID               |
| ResourceId      | string   | Unique resource ID                  |
| SKU             | string   | Pricing tier, (e.g. Free, Standard, Premium, MessageCount, MessageCountPremium)  |
| Quantity        | real     | Usage quantity                      |

### 4.2 `FeatureTrackV2_Daily` and `FeatureTrackV2_EU_Daily`

> Same schema, separate data regions — use union for full analysis.

| Column          | Type     | Description                         |
|-----------------|----------|-------------------------------------|
| Date            | datetime | Feature usage date                  |
| Feature         | string   | Feature name                        |
| Category        | string   | Feature category                    |
| ResourceId      | string   | Unique resource ID                  |
| SubscriptionId  | string   | Azure subscription ID               |
| Properties      | string   | Additional metadata                 |
| RequestCount    | long     | Number of feature requests          |

### 4.3 `RPSettingLatest`

The `RPSettingLatest` table stores the **latest known configuration state** for each resource, as of its last update (`LastUpdated`).  
Key characteristics:

- **Snapshot Table**: It reflects the **most recently observed state** per resource, **not** daily updates.
- **Historical Data**: Many records may belong to **deleted or inactive resources**, making it unsuitable for standalone time-based analysis (e.g., counting resources in a given month).
- **Recommended Usage**: Use this table in **joins with daily tables** (e.g., `BillingUsage_Daily`, `ResourceMetrics`) to enrich resource-level analytics with configuration context.
  - Example: Filter April resources using `BillingUsage_Daily` and then join to `RPSettingLatest` to analyze how many were in Serverless mode.

> WARN: Always apply filters like `LastUpdated > ago(30d)` or join with active usage tables to avoid including outdated or irrelevant resource entries.

| Column Name             | Type     | Description                                          |
|-------------------------|----------|------------------------------------------------------|
| ResourceId              | string   | Unique identifier of the SignalR resource.           |
| Region                  | string   | Azure region where the resource is deployed.         |
| SKU                     | string   | Stock Keeping Unit of the resource. (e.g. Free_F1, Standard_S1, Standard_S2, Premium_P1, Premium_P2)  |
| Kind                    | string   | The kind of the SignalR resource. (e.g. SocketIO)    |
| State                   | string   | Current state of the resource (e.g., Succeeded, Failed, Updating, etc.). |
| ServiceMode             | string   | Mode of the service (e.g., Default, Serverless, Classic). Note it doesn't apply to SocketIO, for SocketIO, see Extras  |
| IsUpstreamSet           | bool     | Indicates if upstream is configured.                 |
| IsEventHandlerSet       | bool     | Indicates if event handler is configured.            |
| EnableTlsClientCert     | bool     | Indicates if TLS client certificate is enabled.      |
| IsPrivateEndpointSet    | bool     | Indicates if a private endpoint is configured.       |
| EnablePublicNetworkAccess | bool   | Indicates if public network access is enabled.       |
| DisableLocalAuth        | bool     | Indicates if local authentication is disabled.       |
| DisableAadAuth          | bool     | Indicates if Azure AD authentication is disabled.    |
| IsServerlessTimeoutSet  | bool     | Indicates if serverless timeout is set.              |
| AllowAnonymousConnect   | bool     | Indicates if anonymous connections are allowed.      |
| EnableRegionEndpoint    | bool     | Indicates if regional endpoint is enabled.           |
| ResourceStopped         | bool     | Indicates if the resource is stopped.                |
| EnableLiveTrace         | bool     | Indicates if live trace is enabled.                  |
| EnableResourceLog       | bool     | Indicates if resource logging is enabled.            |
| LastUpdated             | datetime | Timestamp of the last update to the settings.        |
| Extras                  | string   | Additional information or metadata. i.e. tags to indicate isAspire or serviceMode especially for socketIO. Sample value: `{"tags":{"isAspire":true},"socketIO":{"serviceMode":"Serverless"}}` |

### 4.4 `ResourceMetrics`

This table contains daily usage statistics for each resource, representing activity such as message throughput and connection counts on a per-day basis (UTC). Each row reflects the actual usage(including zero value) of a specific resource on a specific day, as long as the resource has not been deleted.
Because data is recorded daily, it can also be used to infer resource existence—i.e., determining the earliest or latest day a resource was active.

| Column              | Type     | Description             |
|---------------------|----------|-------------------------|
| Date                | datetime | Metric date             |
| Region              | string   | Azure region            |
| ResourceId          | string   | Resource ID             |
| SumMessageCount     | real     | Total messages          |
| MaxConnectionCount  | real     | Peak connections        |
| AvgConnectionCount  | real     | Average connections     |
| SumSystemErrors     | real     | System error count      |
| SumTotalOperations  | real     | Total operations        |

### 4.5 `SubscriptionMappings`

This table represents a global **snapshot** of all Azure subscriptions, including their properties such as tenant ID, customer type, commerce details. Each row corresponds to a subscription at its latest known state.

> ⚠️ This table is **not intended to be used as a primary table** for product-specific analysis, as it contains data across all Azure services and may include subscriptions unrelated to the target product.
> 
> Instead, it should be **joined** with other usage or billing tables (e.g., `BillingUsage_Daily`, `ResourceMetrics`) via `SubscriptionId` to enrich the context with properties such as:
> - Whether the subscription is external or internal.
> - Billing type.
> - Tenant segmentation.
> - Additional customer metadata.

| Column Name       | Type   | Description                                                   |
|-------------------|--------|---------------------------------------------------------------|
| P360_ID           | string | Internal classification                                       |
| CloudCustomerGuid | string | Customer-level GUID                                           |
| SubscriptionId    | string | Azure subscription ID                                         |
| CustomerType      | string | e.g., Internal, External                                      |
| SegmentName       | string | e.g., Microsoft Internal, Major Commercial, etc.              |
| OfferType         | string | Azure offer type associated with the subscription             |
| OfferName         | string | Human-readable name of the offer                              |
| BillingType       | string | e.g., Internal, External - Billable, External Non - Billable  |
| CustomerName      | string | Customer or organization name                                 |
| WorkloadType      | string | e.g., DevTest, Production, etc.                               |
| S500              | string | S500 customer classification (e.g., Yes or No).               |

### 4.6 `CSSTicketsByStartTime(startDate:datetime)`
This is a custom kusto function to get SignalR and Web PubSub customer support tickets metadata. Each row represents a unique support case.

| Column Name         | Type       | Description                                                                 |
|---------------------|------------|-----------------------------------------------------------------------------|
| IncidentId          | string     | Unique identifier for the support incident.                                 |
| CreatedDateTime     | datetime   | Timestamp when the incident was first created.                              |
| State               | string     | Current state of the incident (e.g., Active, Resolved).                     |
| Severity            | string     | Assigned severity level (e.g. A, B, C) indicating urgency.                  |
| SupportCountry      | string     | Country associated with the support request origin.                         |
| Title               | string     | Short title or summary of the incident.                                     |
| Status              | string     | Descriptive status of the case (e.g. Troubleshooting, Mitigated, Resolved). |
| SupportProductName  | string     | Specific product under support request (e.g., Azure SignalR Service, Azure Web PubSub Service). |
| Customer            | string     | Customer organization or account associated with the incident.              |
| RegionName          | string     | Azure region tied to the resource or support context (e.g., East US).       |
| ResourceUri         | string     | Full resource URI that was impacted by the incident.                        |

## 5. Common Analytical Scenarios

- **Active Resources**: Analyze `MaxConnectionCount` with at least 1 connection in a day to assess user engagement.
- **Message Throughput**: Use `SumMessageCount` to evaluate message throughput.
- **Feature Usage**: Use `FeatureTrackV2_Daily` and `FeatureTrackV2_EU_Daily` to understand which features are most used.
- **Billing Analysis**: Use `BillingUsage_Daily` and SKU info for revenue estimation.
- **Configuration Status**: Use `RPSettingLatest` to identify resource configurations.

## 6. Common Filters and Definitions

### 6.1 AI-Related Resources

Filter SignalR resources that are likely associated with AI workloads based on `ResourceId` naming conventions:

```Kusto
// Apply when a ResourceId field is available
| where ResourceId has 'gpt' or 
       ResourceId has 'ai' or 
       ResourceId has 'ml' or 
       ResourceId has 'cognitive' or 
       ResourceId contains 'openai' or 
       ResourceId contains 'chatgpt'
```

### 6.2 Revenue Estimation
Estimate revenue from daily usage using SKU-based unit pricing. The following example uses the `BillingUsage_Daily` table.

```Kusto
| extend Revenue = case(
    SKU == 'Free', 0.0,
    SKU == 'Standard', 1.61,
    SKU == 'Premium', 2.0,
    1.0  // MessageCount and MessageCountPremium
) * Quantity
```

### 6.3 Excluding Internal/Test Resources
Always exclude internal or test subscriptions to focus on real customer behavior. This filter must be applied in nearly all analytical scenarios unless the user explicitly requests internal analysis.

```Kusto
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
```

### 6.4 Customer-Level Join

```Kusto
| join kind = inner SubscriptionMappings on SubscriptionId
```

### 6.5 **Active** Resource
A resource is considered active on a given day if it has at least one connection recorded.

This definition is applied when using or joining the `ResourceMetrics` table:

```Kusto
| where MaxConnectionCount > 0
```

> WARN: Only apply this filter **when the user's question explicitly involves active users or active usage**. Do not filter out inactive resources by default unless the term "active" is clearly mentioned in the user prompt.


## 7. Notes and Considerations

- All timestamps are in **UTC**.
- Data refresh is **daily** with ~2 hours delay.
- The latest available data is typically as of `startofday(now(), -1)`, due to processing delays. When answering user questions involving time ranges such as "recent X days" or "rolling X days", always use this as the effective end date to ensure accuracy.
- Use filter `| where ResourceId has '/Microsoft.SignalRService/SignalR/'` for SignalR and `| where ResourceId has '/Microsoft.SignalRService/WebPubSub/'` for Web PubSub to filter specific service resource. Focus analysis on a single service type based on the question's context, unless the user explicitly requests to include both service types tegother in the same analysis.
- Always use `ResourceMetrics`, `BillingUsage_Daily` or (`FeatureTrackV2_Daily` union `FeatureTrackV2_EU_Daily`) as the primary data source table when answering product usage questions, e.g. total revenue, customer count, sum messages, etc.. Never use `RPSettingLatest` or `SubscriptionMappings` directly for counting resources or customers, as these are **snapshot tables** and do **not** reflect time-based usage accurately.
- If `SubscriptionId` is not an available column in the data table, it can be parsed from `ResourceId`, e.g. `| parse ResourceId with "/subscriptions/" SubscriptionId:string "/resourceGroups/" *`.
- For **customer-level analysis**, always join `SubscriptionMappings` to access `CustomerName`, `CustomerType`, `BillingType`, or compute metrics like `dcount(CloudCustomerGuid)`.
- Carefully interpret user references to **"external"** or **"external billable"**. If the context relates to customer segmentation or general usage (e.g., "external users"), prefer filtering by `CustomerType == "External"`. If the context involves billing, revenue, or the user explicitly mentions **external billable**, prefer filtering by `BillingType == "External - Billable"`.
- For performance, unless the user explicitly specifies otherwise, limit query time ranges to **the most recent 30 days** for general status questions and **the most recent 6 months/weeks** for monthly/weekly trend analysis, and limit result rows to **≤ 20**(e.g., | top 20 by `<some-property>`).
- Always exclude usage from internal engineering subscriptions (e.g. `| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)`) to focus on external customer behavior.


## 8. Query Samples

### 8.1 Top external billable customers (SignalR + Web PubSub together) by Average Connection Count in Last 28d

```Kusto
let endDate = startofday(now(), -1);
let startDate = endDate - 27d;
// specified external billable filter and Considerations filter
let customer_filter = SubscriptionMappings
    | where BillingType == 'External - Billable' and SubscriptionId !in (SignalRTeamInternalSubscriptionIds);
ResourceMetrics
| where Date between (startDate .. endDate)
| parse ResourceId with "/subscriptions/" SubscriptionId:string "/resourceGroups/" *
| join kind=inner (customer_filter) on SubscriptionId
| summarize AvgConnectionCount = sum(AvgConnectionCount) by CloudCustomerGuid, CustomerName, Date
| summarize AvgConnectionCount = avg(AvgConnectionCount) by CloudCustomerGuid, CustomerName
// If not specified, use default 20 records
| top 20 by AvgConnectionCount desc  
```

### 8.2 Top external SignalR customers by Revenue

```Kusto
// If not specified, use default 30d time window
let endDate = startofday(now(), -1);
let startDate = endDate - 29d;
// specified external CustomerType filter per description and Considerations filter
let customer_filter = SubscriptionMappings
    | where CustomerType == 'External' and SubscriptionId !in (SignalRTeamInternalSubscriptionIds);
BillingUsage_Daily
| where Date between (startDate .. endDate)
// Specify SignalR resource
| where ResourceId has '/Microsoft.SignalRService/SignalR/'
| parse ResourceId with "/subscriptions/" SubscriptionId:string "/resourceGroups/" *
| join kind=inner (customer_filter) on SubscriptionId
// calculate revenue
| extend Revenue = case(
    SKU == 'Free', 0.0,
    SKU == 'Standard', 1.61,
    SKU == 'Premium', 2.0,
    1.0  // MessageCount and MessageCountPremium
) * Quantity
// group by CloudCustomerGuid as unique identifier and CustomerName as readable string.
| summarize Revenue = sum(Revenue) by CloudCustomerGuid, CustomerName
// If not specified, use default 20 records
| top 20 by Revenue desc
```

### 8.3 Active SignalR Resource Count weekly trend by SKU

```Kusto
// If not specified, use default 6 weeks time window for a weekly trend case
let endDate = startofweek(now()) - 1d;
let startDate = startofweek(endDate, -5);
ResourceMetrics
| where Date between (startDate .. endDate)
// Specify SignalR resource
| where ResourceId has '/Microsoft.SignalRService/SignalR/'
// Exclude internal subs
| parse ResourceId with "/subscriptions/" SubscriptionId:string "/resourceGroups/" *
// Filter out internal resources.
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
// Use "Active" definition: any day with at least one connection
| where MaxConnectionCount > 0
// join BillingUsage_Daily to get SKU metadata
| join kind = inner (BillingUsage_Daily) on Date, ResourceId
// For each resource and week, pick the most recent SKU to avoid double counting
| summarize SKU = max(SKU) by Week = startofweek(Date), ResourceId
// Count distinct active resources per week and SKU
| summarize ActiveResource = dcount(ResourceId) by Week, SKU
```