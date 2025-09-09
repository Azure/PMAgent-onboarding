# Test - Product and Data Overview Template

## 1. Product Overview

Test is a placeholder product for onboarding demonstration. The queries provided cover usage, reliability, retention, revenue, and feature tracking for Azure SignalR and Web PubSub services.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**: Test (SignalR/WebPubSub)
- **Product Nick Names**: 
> **[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations.
- **Kusto Cluster**: signalrinsights.eastus2
- **Kusto Database**: SignalRBI
- **Access Control**:
> **[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed **groups/users** here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  
- **Primary Metrics**: 
  - MaxConnectionCount
  - MessageCount
  - Revenue
  - QoS (Quality of Service)
  - Retention (Customer, Subscription, Resource)
  - Feature Usage (e.g., AutoScale, SocketIO, Aspire)
> **[TODO]Data_Engineer**: Review and supplement key metrics used to measure product performance, usage, or customer behavior.

## 3. Table Schemas in Azure Data Explorer

### 3.1 OperationQoS_Daily

| Column          | Type     | Description            |
|-----------------|----------|------------------------|
| env_time        | datetime | Event timestamp        |
| resourceId      | string   | Resource identifier    |
| env_cloud_location | string | Azure region          |
| env_cloud_role  | string   | Resource role          |
| totalTimeSec    | long     | Total time in seconds  |
| totalUpTimeSec  | long     | Uptime in seconds      |

### 3.2 ConnectivityQoS_Daily

| Column          | Type     | Description            |
|-----------------|----------|------------------------|
| env_time        | datetime | Event timestamp        |
| resourceId      | string   | Resource identifier    |
| env_cloud_location | string | Azure region          |
| env_cloud_role  | string   | Resource role          |
| totalTimeSec    | long     | Total time in seconds  |
| totalUpTimeSec  | long     | Uptime in seconds      |

### 3.3 MaxConnectionCount_Daily

| Column          | Type     | Description            |
|-----------------|----------|------------------------|
| Date            | datetime | Date of measurement    |
| Role            | string   | Resource role          |
| MaxConnectionCount | long  | Maximum connection count |
| SubscriptionId  | string   | Subscription identifier |
| Region          | string   | Azure region           |

### 3.4 BillingUsage_Daily

| Column          | Type     | Description            |
|-----------------|----------|------------------------|
| Date            | datetime | Billing date           |
| ResourceId      | string   | Resource identifier    |
| SubscriptionId  | string   | Subscription identifier|
| SKU             | string   | Service SKU            |
| Quantity        | long     | Usage quantity         |
| Revenue         | real     | Calculated revenue     |
| BillingType     | string   | Billing type           |
| CustomerType    | string   | Customer classification|

### 3.5 SubscriptionMappings

| Column          | Type     | Description            |
|-----------------|----------|------------------------|
| SubscriptionId  | string   | Subscription identifier|
| CustomerType1   | string   | Customer type          |
| SegmentName     | string   | Segment name           |

### 3.6 FeatureTrackV2_Daily

| Column          | Type     | Description            |
|-----------------|----------|------------------------|
| Date            | datetime | Feature event date     |
| Feature         | string   | Feature name           |
| RequestCount    | long     | Number of requests     |
| ResourceId      | string   | Resource identifier    |
| SubscriptionId  | string   | Subscription identifier|

> **[TODO]Data_Engineer**: Review and add any additional tables or columns relevant to your product.

## 4. Common Analytical Scenarios

- **Quality of Service (QoS) Analysis**: Calculate uptime ratios and SLA attainment for resources by region and overall.
- **Service Usage**: Weekly/monthly aggregation of max connections, message counts, outbound traffic.
- **Retention Analysis**: Monthly/weekly retention rates for subscriptions, customers, and resources.
- **Revenue and Billing**: Monthly/weekly/daily revenue and paid unit calculations by SKU, customer type, and billing type.
- **Feature Adoption**: Track usage of features like AutoScale, SocketIO, Aspire, and event handler errors.
- **Churn and Conversion**: Analyze customer churn rates and conversion from free to paid tiers.
- **Top Customers/Subscriptions**: Identify top customers/subscriptions by usage, revenue, and growth.

> **[TODO]Data_Engineer**: Review or supplement this section with representative product usage scenarios that are often investigated.

## 5. Common Filters and Definitions

### 5.1 Excluding Internal/Test Resources

```Kusto
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
```

### 5.2 Product filter

```Kusto
| where ResourceId has '/signalr/' // for SignalR
| where ResourceId contains 'webpubsub' // for WebPubSub
```

### 5.3 Revenue Logic

```Kusto
| extend Revenue = case(SKU == 'Free', 0.0, SKU == 'Standard', 1.61, SKU == 'Premium', 2.0, 1.0) * Quantity
```

### 5.4 Customer Segmentation

```Kusto
| join kind = leftouter SubscriptionMappings on SubscriptionId
| extend CustomerType = CustomerType1
```

### 5.5 Feature Mapping

```Kusto
| extend Feature = case(
    Feature in ('AutoScale', 'SocketIO', 'Aspire'), Feature,
    'Other')
```

> **[TODO]Data_Engineer**: Review or add product specific and common known filters.

## 6. Notes and Considerations

> **[TODO]Data_Engineer**: **Content Guidance**: Include important operational notes, data limitations, and analysis best practices specific to this product. This section helps PMAgent perform self-checks and make accurate decisions during analysis.

- All timestamps are in **UTC**.
- The latest available data is typically as of `now()` or `startofday(now())`.
- For performance, limit query ranges to **<6 months** and results to **≤20 rows**.
- For accuracy, use `count_distinct()` to count distinct identifiers.
- Always exclude usage from internal engineering subscriptions (e.g. `| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)`) to focus on external customer behavior.

## 7. Sample Queries

### 7.1 Calculate latest rolling 28d QoS for SignalR

```Kusto
OperationQoS_Daily
| where env_time > ago(28d) and resourceId has '/signalr/'
| summarize Qos = iif(sum(totalTimeSec) == 0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec)) by Date = env_time, Region = env_cloud_location
```

### 7.2 Calculate monthly revenue by SKU

```Kusto
BillingUsage_Daily
| where Date >= startofmonth(now(), -12) and SubscriptionId !in (SignalRTeamInternalSubscriptionIds) and ResourceId has '/signalr/'
| extend Revenue = case(SKU == 'Free', 0.0, SKU == 'Standard', 1.61, SKU == 'Premium', 2.0, 1.0) * Quantity
| summarize BillingNormalizedRevenue = sum(Revenue) by DateKey = startofmonth(Date), SKU, CustomerType, BillingType
```

### 7.3 Retention analysis for subscriptions

```Kusto
SubscriptionRetentionSnapshot
| where StartDate >= datetime_add('year', -1, startofmonth(now()))
| extend StartMonth = startofmonth(StartDate)
| summarize Retain = dcount(SubscriptionId) by StartMonth
```
