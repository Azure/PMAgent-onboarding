# SignalR and Web PubSub BI - Product and Data Overview Template

## 1. Product Overview

This schema onboards the SignalR and Web PubSub BI product into PMAgent. It covers business reporting and operational QoS analytics for Azure SignalR Service and Azure Web PubSub, focusing on daily/weekly/monthly aggregates and cached snapshots used for usage, revenue, adoption, and QoS insights. Many analyses enrich fact tables with subscription/customer dimensions and resource configuration snapshots. This draft will enable PMAgent to interpret and query the product’s Azure Data Explorer sources consistently.

## 2. Data Platform Overview

- Data Storage: Azure Data Explorer (ADX)
- Product: SignalR and Web PubSub BI
- Product Nick Names: 
  - [TODO]Data_Engineer: Fill in commonly used short names or abbreviations for the product (e.g., "ASRS", "SignalR", "AWPS", "WebPubSub", "WPS") to help PMAgent accurately recognize the target product from user conversations.
- Kusto Cluster:
  - signalrinsights.eastus2
- Kusto Database:
  - SignalRBI
- Access Control:
  - [TODO] Data Engineer: If this product’s data has high confidentiality concerns, please specify the allowed groups/users here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.

-----

# Kusto Query Playbook: SignalR and Web PubSub BI

## Overview
Product: SignalR and Web PubSub BI

Scope: Business reporting and operational QoS analytics for Azure SignalR Service and Azure Web PubSub. Tables are largely daily/weekly/monthly aggregates and cached snapshots used for usage, revenue, adoption, and QoS. Many analyses require enriching fact tables with subscription/customer dimensions and resource configuration snapshots.

Cluster: signalrinsights.eastus2
Database: SignalRBI
Alternates: Additional cross-cluster sources are used for specific scenarios (ARM control-plane logs and VS WebTools telemetry).

## Conventions & Assumptions

- Time semantics
  - Observed timestamp columns
    - Date (daily facts): BillingUsage_Daily, MaxConnectionCount_Daily, SumMessageCount_Daily, FeatureTrack family, QoS daily tables, runtime grouped tables.
    - Week (weekly snapshots, weekly conversion).
    - Month (monthly snapshots, churn).
    - TimeStamp/TIMESTAMP (snapshots and cross-sources).
    - env_time (QoS tables with env_* schema).
    - DateHour (string, hourly Redis errors).
    - StartDate/EndDate (period boundaries in some cached snapshots).
    - AdvancedServerTimestampUtc (cross-source VS WebTools).
  - Canonical Time Column
    - Use TimeCol as canonical in your queries.
    - Alias examples:
      - Daily: | project-rename TimeCol = Date
      - Weekly: | project-rename TimeCol = Week
      - Monthly: | project-rename TimeCol = Month
      - QoS env: | project-rename TimeCol = env_time
      - Hourly Redis: | extend TimeCol = todatetime(DateHour)
      - Cross-source ARM: | project-rename TimeCol = TIMESTAMP
      - Cross-source VS WebTools: | project-rename TimeCol = AdvancedServerTimestampUtc
  - Typical windows and binning
    - Windows: last 28–60 days; last 26 weeks; startofmonth(..) to startofmonth(..) for monthly.
    - Binning: bin(TimeCol, 1d), startofweek(TimeCol), startofmonth(TimeCol). For hourly, bin(TimeCol, 1h) or startofday(TimeCol) as needed.
  - Timezone
    - Unknown. Treat data as UTC by default. Be cautious using “today”; latest partitions may be incomplete.

- Freshness & Completeness Gates
  - Batch-produced daily/weekly/monthly facts and snapshots. Current-day partition may be incomplete until the batch finishes.
  - Recommended effective end time
    - Use the previous full day or last complete partition instead of now().
    - Example: let EffectiveEnd = startofday(ago(1d));
  - Multi-slice completeness gate pattern (example)
    - Choose a sentinel fact (e.g., MaxConnectionCount_Daily) and require at least <MinRegions> distinct regions before using a date as complete:
      - let MinRegions = <MinRegions>;
      - let EndGate = toscalar(MaxConnectionCount_Daily
          | where Date >= ago(30d)
          | summarize Regions=dcount(Region) by Date
          | where Regions >= MinRegions
          | summarize arg_max(Date, Regions)
          | project Date);
      - let EffectiveEnd = iff(isnull(EndGate), startofday(ago(1d)), EndGate);

- Joins & Alignment
  - Keys
    - SubscriptionId, ResourceId (or Role normalized to root resource), CloudCustomerGuid (from SubscriptionMappings/CustomerModel), Region.
  - Resource normalization
    - Role may include “/replicas/…”. Normalize to resource root and lowercase:
      - extend ResourceIdNorm = tolower(iif(Role has "/replicas/", substring(Role, 0, indexof(Role, "/replicas/")), Role))
  - Typical join kinds
    - SubscriptionMappings: join kind=inner on SubscriptionId (enforces available customer metadata).
    - RPSettingLatest: join kind=leftouter on normalized ResourceId (point-in-time config).
  - Post-join hygiene
    - Resolve duplicates with project-rename and coalesce().
    - Drop unused columns via project-away to avoid ambiguity.

- Filters & Idioms
  - Service/product scoping
    - ResourceId/Role has/contains “microsoft.signalrservice/signalr” or “/signalr/” for SignalR.
    - ResourceId/Role has/contains “microsoft.signalrservice/webpubsub” or “/webpubsub/” for Web PubSub.
  - Tenancy filtering
    - Exclude internal subscriptions: where SubscriptionId !in (SignalRTeamInternalSubscriptionIds()).
  - Cohorts
    - Build allowlists/denylists in CTEs (let blocks), then join kind=inner to apply.

- Cross-cluster/DB & Sharding
  - Qualify external sources explicitly:
    - cluster("armprodgbl.eastus").database("<ARM_DB>").Requests
    - cluster("armprodgbl.eastus").database("<ARM_DB>").HttpIncomingRequests
    - cluster("ddtelinsights").database("<DDTEL_DB>").WebTools_Raw
  - Same-schema shards/variants
    - union tables → normalize keys/time → summarize. Ensure ResourceId is normalized before aggregate.

- Table classes and when to use
  - Fact (daily/hourly): BillingUsage_Daily, MaxConnectionCount_Daily, SumMessageCount_Daily, FeatureTrack*, BoundTraffic_Daily, QoS daily, runtime groups/transports, Redis/Runtime exceptions hourly.
    - Use for flexible windows and recomputed KPIs.
  - Snapshot (point-in-time cached): Cached_* and Retention*Snapshot families.
    - Use for dashboards/OKRs where speed matters; avoid when customizing time ranges not covered by the snapshot.
  - Function-backed
    - TopSubscriptions, Flow functions: dynamic but heavier. Prefer cached snapshots for dashboards.

## Entity & Counting Rules (Core Definitions)

- Entity model
  - Resource → Subscription → Customer
    - Resource: ResourceId (lowercased, no “/replicas/” segment).
    - Subscription: SubscriptionId (GUID).
    - Customer/Tenant: CloudCustomerGuid (from SubscriptionMappings or CustomerModel); P360_ID/C360_ID for CRM linkages.
  - Standard grouping levels
    - By ResourceId for resource-level load/QoS.
    - By SubscriptionId for business segmentation and top-N.
    - By CloudCustomerGuid or P360/C360 for customer-level reporting.

- Counting rules
  - Daily facts
    - MaxConnectionCount_Daily: use max over a week/month for “peak” KPIs.
    - SumMessageCount_Daily / BoundTraffic_Daily: use sum over the period for totals.
    - AvgConnectionCountEP_Daily: use max of daily averages if constructing weekly maxima of avg endpoint load.
  - Snapshots
    - Use as-is for period-defined snapshots (StartDate/EndDate columns define the window in some cached tables).
  - De-duplication
    - Use summarize arg_max(TimeCol, *) by <key> to get latest record per key.
  - Do/Don’t
    - Do not mix max and sum across rollups incorrectly (e.g., don’t sum daily max connections to get weekly peak; take max).
    - Do not treat RPSettingLatest as historical; it is a point-in-time snapshot.

- Business definitions
  - Revenue mapping (use placeholders, don’t hardcode prices):
    - Revenue = case(SKU == "Free", 0.0, SKU == "Standard", <UnitPrice_Standard>, SKU == "Premium", <UnitPrice_Premium>, <UnitPrice_Fallback>) * Quantity

## Canonical Tables
Cluster: signalrinsights.eastus2, Database: SignalRBI
Product scope: SignalR and Web PubSub. Tables are largely daily/weekly/monthly aggregates and cached snapshots for business reporting and operational QoS.

General guidance
- Timezone: unknown. Treat current-day data as possibly incomplete.
- Freshness: “Daily/Weekly/Monthly” and “Snapshot” tables are batch-produced. Assume end-of-period availability but treat latest partition as potentially partial.
- Tenancy filtering: Most business usage queries exclude internal subscriptions via SignalRTeamInternalSubscriptionIds() and join to SubscriptionMappings for enrichment.
- Resource scoping: Use Role/ResourceId pattern matching:
  - SignalR: resourceId/Role contains/has 'microsoft.signalrservice/signalr' or '/signalr/'
  - Web PubSub: resourceId/Role contains/has 'microsoft.signalrservice/webpubsub' or '/webpubsub/'
- ResourceId normalization: When Role includes '/replicas/', normalize to the resource root (substring up to '/replicas/'), and tolower().
- Cost mapping: When computing revenue, do not hardcode numbers. Use placeholders:
  - Revenue = case(SKU == 'Free', 0.0, SKU == 'Standard', <UnitPrice_Standard>, SKU == 'Premium', <UnitPrice_Premium>, <UnitPrice_Fallback>) * Quantity

Order: High priority first, then Normal, then Low.

---

### Table name: BillingUsage_Daily
- Priority: High
- What this table represents: Daily aggregate billing usage per resource/subscription SKU. Zero rows for a resource/day implies no billable usage recorded.
- Freshness expectations: Daily batch; latest date may be incomplete until the batch finishes.
- When to use / When to avoid:
  - Use: Monthly revenue/usage rollups (by SKU/CustomerType/BillingType), revenue trend by product (SignalR vs Web PubSub) when filtered by ResourceId.
  - Use: Excluding internal subscriptions in business reporting.
  - Avoid: Real-time usage; per-operation metrics; QoS.
- Similar tables & how to choose:
  - Cached_ZnOKREstRevenueWeekly/Monthly_Snapshot: pre-aggregated OKR views; use for dashboard speed.
  - KPI tables: higher-level KPI rollups; use if you only need top-line numbers.
- Common Filters:
  - Date range constraints (e.g., Date >= startofmonth(...), Date <= computed EndDate)
  - ResourceId has '/signalr/' or '/webpubsub/'
  - SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
  - Join to SubscriptionMappings for CustomerType, BillingType, SegmentName
- Table columns:

  | Column     | Type     | Description or meaning |
  |------------|----------|------------------------|
  | Date       | datetime | Usage day. |
  | Region     | string   | Azure region of the resource. |
  | SubscriptionId | string | ARM subscription GUID. |
  | ResourceId | string   | ARM resourceId; filter for service kind. |
  | SKU        | string   | Free, Standard, Premium. |
  | Quantity   | real     | Daily billable units. |

- Column Explain:
  - Date: partition key for time-based rollups.
  - ResourceId: identify service type and resource scope; apply has/contains filters.
  - SKU: used in Revenue cost mapping; segmenting Free vs paid.
  - Quantity: core measure for billing/revenue computations.

---

### Table name: MaxConnectionCount_Daily
- Priority: High
- What this table represents: Daily aggregate of max concurrent connections per resource (and sometimes per day’s peak). Zero rows indicate no connection activity for that day.
- Freshness expectations: Daily batch aggregation.
- When to use / When to avoid:
  - Use: Weekly maxima for connection peaks by CustomerType/ServiceMode/BillingType.
  - Use: Active resource/subscription/customer counts (distinct by Role/SubscriptionId/CloudCustomerGuid after join).
  - Avoid: Average connection load across endpoints (use AvgConnectionCountEP_Daily).
- Similar tables & how to choose:
  - AvgConnectionCountEP_Daily: average vs max; choose based on KPI definition.
  - SumMessageCount_Daily: message volume instead of connections.
- Common Filters:
  - Date windows (e.g., last 26 weeks)
  - Role has 'microsoft.signalrservice/signalr' OR '.../webpubsub'
  - Normalize Role to ResourceId (strip '/replicas')
  - Join RPSettingLatest, SubscriptionMappings; exclude internal subscriptions.
- Table columns:

  | Column            | Type     | Description or meaning |
  |-------------------|----------|------------------------|
  | Date              | datetime | Aggregation date. |
  | Role              | string   | Resource scope (may include '/replicas'). |
  | SubscriptionId    | string   | ARM subscription GUID. |
  | CustomerType      | string   | Customer classification (e.g., Internal/External). |
  | Region            | string   | Azure region. |
  | MaxConnectionCount| long     | Daily maximum connection count. |

- Column Explain:
  - Role: convert to lowercase, strip replicas for resource-level mapping.
  - MaxConnectionCount: primary metric for “peak” analysis.
  - CustomerType/Region: segment analysis.

---

### Table name: SumMessageCount_Daily
- Priority: High
- What this table represents: Daily aggregate of total messages. Zero rows imply no messaging activity for that day.
- Freshness expectations: Daily batch.
- When to use / When to avoid:
  - Use: Weekly total messages by CustomerType/ServiceMode/BillingType.
  - Use: Top-subscription trend analysis (with Cached_TopSubscriptions_Snapshot).
  - Avoid: Transport breakdown; endpoint averages (use RuntimeTransport_Daily; AvgConnectionCountEP_Daily).
- Similar tables & how to choose:
  - BoundTraffic_Daily (Web PubSub): use MetricName 'OutboundTraffic' for egress-focused KPI.
- Common Filters:
  - Date windows, Role service kind filter
  - Joins with RPSettingLatest, SubscriptionMappings
- Table columns:

  | Column         | Type     | Description or meaning |
  |----------------|----------|------------------------|
  | Date           | datetime | Aggregation date. |
  | Role           | string   | Resource identifier (may include '/replicas'). |
  | Region         | string   | Azure region. |
  | SubscriptionId | string   | ARM subscription GUID. |
  | CustomerType   | string   | Customer class. |
  | MessageCount   | long     | Total messages per day. |

- Column Explain:
  - Role/SubscriptionId: resource/sub mapping.
  - MessageCount: core volume KPI.

---

### Table name: SubscriptionMappings
- Priority: High
- What this table represents: Enrichment dimension mapping subscription/customer attributes.
- Freshness expectations: Updated on changes in CRM mappings; operational lag unknown.
- When to use / When to avoid:
  - Use: Enrich business metrics with CustomerType, SegmentName, OfferType, BillingType.
  - Avoid: Treating any metric columns; it’s a dimension join only.
- Similar tables & how to choose:
  - CustomerModel: broader customer view; use depending on field availability needed.
- Common Filters:
  - Join on SubscriptionId (case-insensitive where appropriate).
- Table columns:

  | Column            | Type     | Description or meaning |
  |-------------------|----------|------------------------|
  | P360_ID           | string   | CRM person/account id. |
  | CloudCustomerGuid | string   | Tenant/customer GUID. |
  | SubscriptionId    | string   | ARM subscription GUID (join key). |
  | CustomerType      | string   | Internal/External/etc. |
  | CustomerName      | string   | Display/customer name. |
  | SegmentName       | string   | Segment/vertical. |
  | OfferType         | string   | Offer type. |
  | OfferName         | string   | Offer name. |
  | BillingType       | string   | EA/PayGo/etc. |
  | WorkloadType      | string   | SignalR/WebPubSub workloads. |
  | S500              | string   | Additional classification. |

- Column Explain:
  - SubscriptionId: primary join to fact tables.
  - CustomerType/BillingType/SegmentName: main segmentation fields.

---

### Table name: CustomerModel
- Priority: High
- What this table represents: Customer-level attributes per subscription/tenant; dimension table.
- Freshness expectations: Updated as CRM data changes; latency unknown.
- When to use / When to avoid:
  - Use: Enrich fact data with P360/C360/SegmentName and SubscriptionCreatedDate.
  - Avoid: As a metric source; use with joins only.
- Similar tables & how to choose:
  - SubscriptionMappings: a lighter mapping; choose based on fields needed.
- Common Filters:
  - Join on SubscriptionId or CloudCustomerGuid.
- Table columns:

  | Column                     | Type     | Description or meaning |
  |----------------------------|----------|------------------------|
  | C360_ID                    | string   | Customer 360 identifier. |
  | CustomerName               | string   | Display name. |
  | CloudCustomerGuid          | string   | Tenant/customer GUID. |
  | CloudCustomerName          | string   | Tenant/customer name. |
  | TPID                       | int      | Partner ID. |
  | TPName                     | string   | Partner name. |
  | CustomerType               | string   | Internal/External/etc. |
  | SubscriptionId             | string   | ARM subscription GUID. |
  | FriendlySubscriptionName   | string   | Friendly sub name. |
  | WorkloadType               | string   | Workload classification. |
  | BillingType                | string   | EA/PayGo/etc. |
  | OfferType                  | string   | Offer type. |
  | OfferName                  | string   | Offer name. |
  | CurrentSubscriptionStatus  | string   | Active/Disabled/etc. |
  | SegmentName                | string   | Segment/vertical. |
  | P360_ID                    | string   | CRM person/account id. |
  | P360_CustomerDisplayName   | string   | CRM display name. |
  | SubscriptionCreatedDate    | datetime | Subscription creation time. |
  | S500                       | string   | Additional classification. |

- Column Explain:
  - CloudCustomerGuid: used for deduping customer counts.
  - SubscriptionCreatedDate: cohorting/retention segmentation.

---

### Table name: FeatureTrackV2_Daily
- Priority: High
- What this table represents: Daily aggregate request counts by feature/category per resource.
- Freshness expectations: Daily batch.
- When to use / When to avoid:
  - Use: Feature usage tracking; adoption by Resource/Subscription.
  - Avoid: EU-only aggregate (use FeatureTrackV2_EU_Daily) or legacy schema (FeatureTrack_Daily).
- Similar tables & how to choose:
  - FeatureTrackV2_EU_Daily: EU-only data.
  - FeatureTrack_Daily: legacy; fewer fields.
- Common Filters:
  - Date range; ResourceId/SubscriptionId scope; Category/Feature filters.
- Table columns:

  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | Date          | datetime | Aggregation date. |
  | Feature       | string   | Feature name. |
  | Category      | string   | Category/tag. |
  | ResourceId    | string   | ARM resource. |
  | SubscriptionId| string   | ARM subscription. |
  | Properties    | string   | JSON/kv detail. |
  | RequestCount  | long     | Requests for feature. |

- Column Explain:
  - Feature/Category: core dimensions for feature adoption.
  - RequestCount: metric for trend analysis.

---

### Table name: FeatureTrackV2_EU_Daily
- Priority: High
- What this table represents: EU-located subset of FeatureTrackV2_Daily.
- Freshness expectations: Daily batch.
- When to use / When to avoid:
  - Use: EU-compliant reporting.
  - Avoid: Global feature tracking (use FeatureTrackV2_Daily).
- Similar tables & how to choose:
  - FeatureTrackV2_Daily: global set.
- Common Filters:
  - Date; Feature/Category; ResourceId/SubscriptionId.
- Table columns: same as FeatureTrackV2_Daily.

  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | Date          | datetime | Aggregation date. |
  | Feature       | string   | Feature name. |
  | Category      | string   | Category/tag. |
  | ResourceId    | string   | ARM resource. |
  | SubscriptionId| string   | ARM subscription. |
  | Properties    | string   | JSON/kv detail. |
  | RequestCount  | long     | Requests for feature. |

- Column Explain:
  - Same as FeatureTrackV2_Daily; use for EU-only reporting.

---

### Table name: FeatureTrack_Daily
- Priority: High
- What this table represents: Legacy daily feature tracking aggregate.
- Freshness expectations: Daily batch.
- When to use / When to avoid:
  - Use: Historical comparisons when V2 coverage doesn’t exist.
  - Avoid: New analysis; prefer V2 tables.
- Similar tables & how to choose:
  - FeatureTrackV2_Daily and EU variant.
- Common Filters:
  - Date; Feature; ResourceId/SubscriptionId.
- Table columns:

  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | Date          | datetime | Aggregation date. |
  | Feature       | string   | Feature name. |
  | ResourceId    | string   | ARM resource. |
  | SubscriptionId| string   | ARM subscription. |
  | RequestCount  | long     | Requests for feature. |

- Column Explain:
  - Feature/RequestCount: core KPI.

---

### Table name: FeatureTrack_AutoScale_Daily
- Priority: High
- What this table represents: Daily counts for autoscale-related requests/events.
- Freshness expectations: Daily batch.
- When to use / When to avoid:
  - Use: Track autoscale adoption/operations by region/resource.
  - Avoid: QoS or non-autoscale features; use other FeatureTrack tables.
- Similar tables & how to choose:
  - FeatureTrackV2_Daily: general features.
- Common Filters:
  - Date; Region; ResourceId/SubscriptionId.
- Table columns:

  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | Date          | datetime | Aggregation date. |
  | Region        | string   | Azure region. |
  | ResourceId    | string   | ARM resource. |
  | SubscriptionId| string   | ARM subscription. |
  | RequestCount  | long     | Autoscale-related activity count. |

- Column Explain:
  - Region/ResourceId: segment autoscale activity by fleet/tenant.

---

### Table name: Cached_TopSubscriptions_Snapshot
- Priority: High
- What this table represents: Cached snapshot of top subscriptions over a period with precomputed KPIs.
- Freshness expectations: Snapshot; schedule unknown (likely daily/weekly).
- When to use / When to avoid:
  - Use: Dashboard top-N with Revenue/Connections/Messages/Resources metrics.
  - Avoid: Near-real-time or custom time windows; compute directly from raw fact tables.
- Similar tables & how to choose:
  - TopSubscriptions / TopSubscriptionsTrends: dynamic functions but heavier; use cached for speed.
- Common Filters:
  - Service == 'SignalR' or 'WebPubSub' prior to joins to daily facts.
- Table columns:

  | Column         | Type     | Description or meaning |
  |----------------|----------|------------------------|
  | SubscriptionId | string   | Subscription key. |
  | Revenue        | real     | Revenue over the cached period. |
  | MaxConnection  | long     | Peak connections over period. |
  | MessageCount   | long     | Total messages over period. |
  | StartDate      | datetime | Period start. |
  | EndDate        | datetime | Period end. |
  | TopRevenue     | real     | Rank/top revenue value. |
  | TopConnection  | long     | Rank/top connection value. |
  | TopMessageCount| long     | Rank/top message value. |
  | Rate           | real     | Relative share/ratio. |
  | Service        | string   | Service type (SignalR/WebPubSub). |

- Column Explain:
  - Revenue/MaxConnection/MessageCount: headline KPIs for ranking.
  - StartDate/EndDate: defines snapshot window.

---

### Table name: Cached_Asrs_TopCustomersWoW_v2_Snapshot
- Priority: High
- What this table represents: Cached top customers (SignalR) with week-over-week metrics and ranking deltas.
- Freshness expectations: Snapshot; likely weekly.
- When to use / When to avoid:
  - Use: Customer leaderboard with rank deltas for SignalR.
  - Avoid: WebPubSub top customers (use AWPS variant).
- Similar tables & how to choose:
  - Cached_Awps_TopCustomersWoW_v2_Snapshot for WebPubSub.
- Common Filters:
  - Category/UsageType if segmenting by metric type.
- Table columns:

  | Column                   | Type     | Description or meaning |
  |--------------------------|----------|------------------------|
  | P360_ID                  | string   | Customer id. |
  | P360_CustomerDisplayName | string   | Customer name. |
  | SKU                      | string   | Free/Standard/Premium. |
  | CustomerType             | string   | Customer classification. |
  | BillingType              | string   | Billing model. |
  | Category                 | string   | Metric category. |
  | CurrentValue             | real     | Current metric value. |
  | P360Url                  | string   | Link to customer. |
  | LastDay                  | datetime | Snapshot as-of date. |
  | UsageType                | string   | Internal/External or billing usage type. |
  | CurrentValue1            | real     | Additional metric value. |
  | PrevValue                | real     | Prior period value. |
  | W3Value                  | real     | 3-week value. |
  | DeltaValue               | real     | WoW delta. |
  | Rank                     | long     | Current rank. |
  | W1Rank                   | long     | Last week rank. |
  | W3Rank                   | long     | 3-week rank. |

- Column Explain:
  - Rank/DeltaValue: quick trend assessment.
  - SKU/BillingType: revenue segmentation.

---

### Table name: Cached_Awps_TopCustomersWoW_v2_Snapshot
- Priority: High
- What this table represents: Cached top customers (WebPubSub) weekly, same schema as ASRS variant.
- Freshness expectations: Snapshot; likely weekly.
- When to use / When to avoid:
  - Use: WebPubSub customer leaderboard.
  - Avoid: SignalR (use ASRS variant).
- Similar tables & how to choose:
  - Cached_Asrs_TopCustomersWoW_v2_Snapshot.
- Common Filters:
  - As needed by metric Category/UsageType.
- Table columns: same as Asrs variant (see above).

---

### Table name: OKRv2021
- Priority: High
- What this table represents: OKR metric timeseries (generic category-value).
- Freshness expectations: Batch; period unknown.
- When to use / When to avoid:
  - Use: Trend lines by category for historical OKRs.
  - Avoid: Current OKRs if newer vintages exist.
- Similar tables & how to choose:
  - OKRv2021_AWPS / OKRv2021_SocketIO: product-specific OKRs.
- Common Filters:
  - Date; Category.
- Table columns:

  | Column   | Type     | Description or meaning |
  |----------|----------|------------------------|
  | Date     | datetime | Measurement date. |
  | Category | string   | OKR category. |
  | Value    | real     | Metric value. |

- Column Explain:
  - Category/Value: plot OKRs by category over time.

---

### Table name: OKRv2021_AWPS
- Priority: High
- What this table represents: OKR timeseries for WebPubSub product.
- Freshness expectations: Batch; unknown cadence.
- When to use / When to avoid:
  - Use: AWPS-specific OKR trend.
- Similar tables & how to choose:
  - OKRv2021 (generic), OKRv2021_SocketIO (SocketIO specific).
- Common Filters: Date; Category.
- Table columns: same as OKRv2021.

---

### Table name: OKRv2021_SocketIO
- Priority: High
- What this table represents: OKR timeseries for SocketIO scenarios.
- Freshness expectations: Batch; unknown cadence.
- When to use / When to avoid:
  - Use: SocketIO-specific OKR trend.
- Similar tables & how to choose: OKR family.
- Common Filters: Date; Category.
- Table columns: same as OKRv2021.

---

### Table name: KPIv2019
- Priority: High
- What this table represents: KPI trend with subscription and resource counts (historical KPI collection).
- Freshness expectations: Batch; unknown cadence.
- When to use / When to avoid:
  - Use: Legacy KPI plots requiring SubscriptionCount/ResourceCount.
  - Avoid: Product-specific KPIs; use KPI_AWPS/KPI_SocketIO.
- Similar tables & how to choose:
  - KPI_AWPS, KPI_SocketIO.
- Common Filters:
  - Date.
- Table columns:

  | Column            | Type     | Description or meaning |
  |-------------------|----------|------------------------|
  | Date              | datetime | KPI date. |
  | SubscriptionCount | long     | Distinct subscriptions. |
  | ResourceCount     | long     | Distinct resources. |

- Column Explain:
  - SubscriptionCount/ResourceCount: top-line adoption KPIs.

---

### Table name: KPI_AWPS
- Priority: High
- What this table represents: AWPS-specific KPI counts.
- Freshness expectations: Batch; unknown cadence.
- When to use / When to avoid:
  - Use: WebPubSub KPI reporting.
- Similar tables & how to choose: KPIv2019, KPI_SocketIO.
- Common Filters: Date.
- Table columns: same as KPIv2019.

---

### Table name: KPI_SocketIO
- Priority: High
- What this table represents: SocketIO-specific KPI counts.
- Freshness expectations: Batch; unknown cadence.
- When to use / When to avoid:
  - Use: SocketIO KPI reporting.
- Similar tables & how to choose: KPIv2019, KPI_AWPS.
- Common Filters: Date.
- Table columns: same as KPIv2019.

---

### Table name: ChurnCustomers_Monthly
- Priority: High
- What this table represents: Monthly churn metrics by service type and SKU cohorts.
- Freshness expectations: Monthly batch.
- When to use / When to avoid:
  - Use: Customer churn trends per month and SKU.
  - Avoid: Weekly conversion; use ConvertCustomer_Weekly.
- Similar tables & how to choose:
  - Retention snapshots for point-in-time retention states.
- Common Filters:
  - Month; ServiceType; SKU.
- Table columns:

  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | Month         | datetime | Month start. |
  | ServiceType   | string   | SignalR/WebPubSub. |
  | Total         | long     | Total customers in cohort. |
  | Churn         | long     | Churned customers. |
  | Standard      | long     | Standard customers count. |
  | StandardChurn | long     | Churned Standard customers. |
  | RunDay        | datetime | Data production time. |

- Column Explain:
  - Churn/StandardChurn: churn KPIs.
  - ServiceType: product split.

---

### Table name: ConvertCustomer_Weekly
- Priority: High
- What this table represents: Weekly conversion funnel between SKUs.
- Freshness expectations: Weekly batch.
- When to use / When to avoid:
  - Use: Free→Paid, Standard→Premium conversion trend.
  - Avoid: Monthly churn; use ChurnCustomers_Monthly.
- Similar tables & how to choose: monthly/retention snapshots for complementary views.
- Common Filters:
  - Week; ServiceType; conversion columns.
- Table columns:

  | Column             | Type     | Description or meaning |
  |--------------------|----------|------------------------|
  | Week               | datetime | Week start. |
  | ServiceType        | string   | Product. |
  | FreeToStandard     | long     | Count of conversions. |
  | TotalCustomers     | long     | Total customers. |
  | StandardCustomers  | long     | Standard customers. |
  | RunDay             | datetime | Data production time. |
  | FreeToPaid         | long     | Free→Paid conversions. |
  | StandardToPremium  | long     | Standard→Premium conversions. |
  | FreeToPremium      | long     | Free→Premium conversions. |
  | PremiumCustomers   | long     | Premium customers. |

- Column Explain:
  - Conversion fields: core weekly KPI.

---

### Table name: Cached_ZnOKRARR_Snapshot
- Priority: High
- What this table represents: Cached ARR OKR snapshot split by product (SignalR/WebPubSub) at a time point.
- Freshness expectations: Snapshot; schedule unknown.
- When to use / When to avoid:
  - Use: ARR OKR snapshots and trends.
- Similar tables & how to choose:
  - Cached_DtOKRARR_Snapshot (different aggregation dimension).
- Common Filters:
  - TimeStamp.
- Table columns:

  | Column   | Type     | Description or meaning |
  |----------|----------|------------------------|
  | TimeStamp| datetime | Snapshot time. |
  | SignalR  | real     | ARR value for SignalR. |
  | WebPubSub| real     | ARR value for WebPubSub. |

- Column Explain:
  - Split by product for OKR tracking.

---

### Table name: Cached_ZnOKREstRevenueWeekly_Snapshot
- Priority: High
- What this table represents: Cached estimated revenue by week and segmentation.
- Freshness expectations: Snapshot; weekly.
- When to use / When to avoid:
  - Use: Faster dashboarding of weekly revenue by SKU/CustomerType/SegmentName/Service.
- Similar tables & how to choose:
  - Monthly/Total variants for different periods.
- Common Filters:
  - Week; SKU; CustomerType; SegmentName; Service.
- Table columns:

  | Column        | Type     | Description or meaning |
  |---------------|----------|------------------------|
  | Week          | datetime | Week start. |
  | SKU           | string   | Plan. |
  | CustomerType  | string   | Segment. |
  | SegmentName   | string   | Segment. |
  | Service       | string   | Product. |
  | Income        | real     | Revenue amount. |

- Column Explain:
  - Income: precomputed revenue (use placeholders for unit prices in ad-hoc recompute).

---

### Table name: Cached_ZnOKREstRevenueMonthly_Snapshot
- Priority: High
- What this table represents: Cached estimated revenue by month; same schema as Weekly with Month granularity.
- Freshness expectations: Monthly snapshot.
- When to use / When to avoid:
  - Use: Monthly revenue dashboards.
- Table columns:

  | Column       | Type     | Description or meaning |
  |--------------|----------|------------------------|
  | Month        | datetime | Month start. |
  | SKU          | string   | Plan. |
  | CustomerType | string   | Segment. |
  | SegmentName  | string   | Segment. |
  | Service      | string   | Product. |
  | Income       | real     | Revenue amount. |

- Column Explain:
  - Same as weekly variant.

---

### Table name: Cached_ZnOKRSubs_Snapshot
- Priority: High
- What this table represents: Cached subscription counts by product; snapshot timeseries.
- Freshness expectations: Snapshot.
- When to use / When to avoid:
  - Use: Subscription count OKRs split by product.
- Table columns:

  | Column   | Type     | Description or meaning |
  |----------|----------|------------------------|
  | TimeStamp| datetime | Snapshot time. |
  | SignalR  | long     | Subscription count. |
  | WebPubSub| long     | Subscription count. |

- Column Explain:
  - Product split.

---

### Table name: Cached_ZnOKRSubsWeekly_Snapshot
- Priority: High
- What this table represents: Weekly subscription counts by SKU/segment/service.
- Freshness expectations: Weekly snapshot.
- When to use / When to avoid:
  - Use: Weekly subscription count dashboards.
- Table columns:

  | Column          | Type  | Description |
  |-----------------|-------|-------------|
  | Week            | datetime | Week start. |
  | SKU             | string   | Plan. |
  | CustomerType    | string   | Segment. |
  | SegmentName     | string   | Segment. |
  | Service         | string   | Product. |
  | SubscriptionCnt | int      | Subscription count. |

- Column Explain:
  - SubscriptionCnt: top-line KPI.

---

### Table name: Cached_ZnOKRSubsMonthly_Snapshot
- Priority: High
- What this table represents: Monthly subscription counts by segmentation.
- Freshness expectations: Monthly snapshot.
- Table columns: same as weekly variant with Month.

  | Column          | Type  | Description |
  |-----------------|-------|-------------|
  | Month           | datetime | Month start. |
  | SKU             | string   | Plan. |
  | CustomerType    | string   | Segment. |
  | SegmentName     | string   | Segment. |
  | Service         | string   | Product. |
  | SubscriptionCnt | int      | Subscription count. |

---

### Table name: Cached_CuOKRConsumption_Snapshot
- Priority: High
- What this table represents: Cached consumption OKR snapshot by product and total.
- Freshness expectations: Snapshot.
- When to use / When to avoid:
  - Use: Consumption KPI by product and total.
- Table columns:

  | Column   | Type     | Description |
  |----------|----------|-------------|
  | TimeStamp| datetime | Snapshot time. |
  | Consumption | real  | Total consumption. |
  | SignalR  | real     | SignalR consumption. |
  | WebPubSub| real     | WebPubSub consumption. |

---

### Table name: Cached_CuOKRConsumptionWeekly_Snapshot
- Priority: High
- What this table represents: Weekly consumption snapshots.
- Table columns:

  | Column       | Type     | Description |
  |--------------|----------|-------------|
  | Week         | datetime | Week start. |
  | SKU          | string   | Plan. |
  | CustomerType | string   | Segment. |
  | SegmentName  | string   | Segment. |
  | Service      | string   | Product. |
  | Consumption  | real     | Consumption value. |

---

### Table name: Cached_CuOKRConsumptionMonthly_Snapshot
- Priority: High
- What this table represents: Monthly consumption snapshots.
- Table columns:

  | Column       | Type     | Description |
  |--------------|----------|-------------|
  | Month        | datetime | Month start. |
  | SKU          | string   | Plan. |
  | CustomerType | string   | Segment. |
  | SegmentName  | string   | Segment. |
  | Service      | string   | Product. |
  | Consumption  | real     | Consumption value. |

---

### Table name: Cached_DtOKRARR_Snapshot
- Priority: High
- What this table represents: Cached ARR OKR snapshot with total.
- Freshness expectations: Snapshot.
- Table columns:

  | Column   | Type     | Description |
  |----------|----------|-------------|
  | TimeStamp| datetime | Snapshot time. |
  | SignalR  | real     | ARR SignalR. |
  | WebPubSub| real     | ARR WebPubSub. |
  | total    | real     | Total ARR. |

---

### Table name: Cached_DtOKREstRevenueWeekly_Snapshot
- Priority: High
- What this table represents: Weekly estimated revenue by usage type (UsageType vs CustomerType).
- Freshness expectations: Weekly snapshot.
- Table columns:

  | Column     | Type     | Description |
  |------------|----------|-------------|
  | Week       | datetime | Week start. |
  | SKU        | string   | Plan. |
  | UsageType  | string   | Internal/External or billing usage type. |
  | SegmentName| string   | Segment. |
  | Service    | string   | Product. |
  | Income     | real     | Revenue amount. |

---

### Table name: Cached_DtOKREstRevenueMonthly_Snapshot
- Priority: High
- What this table represents: Monthly estimated revenue by usage type.
- Freshness expectations: Monthly snapshot.
- Table columns:

  | Column     | Type     | Description |
  |------------|----------|-------------|
  | Month      | datetime | Month start. |
  | SKU        | string   | Plan. |
  | UsageType  | string   | Internal/External or billing usage type. |
  | SegmentName| string   | Segment. |
  | Service    | string   | Product. |
  | Income     | real     | Revenue amount. |

---

### Table name: TopSubscriptionsTrends
- Priority: High
- What this table represents: Trend data for top subscriptions (schema not resolved in this environment).
- Freshness expectations: Likely daily/weekly batch; unknown.
- When to use / When to avoid:
  - Use: Trend lines for top-N subscriptions; if unavailable, derive from daily facts + Cached_TopSubscriptions_Snapshot.
- Similar tables & how to choose:
  - Cached_TopSubscriptions_Snapshot for snapshot KPIs.
- Common Filters:
  - SubscriptionId; Date.
- Table columns:
  - Schema unavailable. Use Cached_TopSubscriptions_Snapshot and daily facts as a fallback.

- Column Explain:
  - N/A (schema unresolved).

---

### Table name: TopSubscriptions (function-backed)
- Priority: High
- What this table represents: Parameterized function producing top subscriptions over a selected endDate window.
- Freshness expectations: Computed on invocation.
- When to use / When to avoid:
  - Use: Dynamic top-N extraction when cached snapshot doesn’t fit.
  - Avoid: Heavy dashboards; prefer Cached_TopSubscriptions_Snapshot.
- Similar tables & how to choose: Cached_TopSubscriptions_Snapshot for cache.
- Common Filters:
  - Provide endDate parameter; optionally other filters by SKU/Service/CustomerType.
- Table columns:
  - Schema unresolved due to function parameters. Use result projection in downstream queries as needed.

---

### Table name: AvgConnectionCountEP_Daily
- Priority: Normal
- What this table represents: Daily average connection count per endpoint (EP) and resource.
- Freshness expectations: Daily batch.
- When to use / When to avoid:
  - Use: Average load analysis; weekly maxima taken via summarize max(SumValue).
  - Avoid: Peak analysis (use MaxConnectionCount_Daily).
- Similar tables & how to choose:
  - MaxConnectionCount_Daily: peak; choose per KPI.
- Common Filters:
  - Date windows; Role has service label; join RPSettingLatest and SubscriptionMappings; exclude internal subscriptions.
- Table columns:

  | Column            | Type     | Description |
  |-------------------|----------|-------------|
  | Date              | datetime | Aggregation date. |
  | Role              | string   | Resource scope (may include '/replicas'). |
  | SubscriptionId    | string   | ARM subscription GUID. |
  | CustomerType      | string   | Customer class. |
  | Region            | string   | Azure region. |
  | Endpoint          | string   | Endpoint identifier. |
  | AvgConnectionCount| long     | Average connections. |

- Column Explain:
  - Endpoint: endpoint-level averages.
  - AvgConnectionCount: main metric.

---

### Table name: BoundTraffic_Daily
- Priority: Normal
- What this table represents: Daily aggregate for bounded metrics like OutboundTraffic (WebPubSub).
- Freshness expectations: Daily batch.
- When to use / When to avoid:
  - Use: OutboundTraffic KPI by week when MetricName == 'OutboundTraffic'.
  - Avoid: Message counts (use SumMessageCount_Daily).
- Similar tables & how to choose:
  - SumMessageCount_Daily for message volume.
- Common Filters:
  - Date window; Role has service label; MetricName == 'OutboundTraffic'; joins to RPSettingLatest and SubscriptionMappings.
- Table columns:

  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Date          | datetime | Aggregation date. |
  | Role          | string   | Resource scope. |
  | Region        | string   | Azure region. |
  | SubscriptionId| string   | ARM subscription. |
  | Endpoint      | string   | Endpoint id. |
  | MetricName    | string   | Metric (e.g., OutboundTraffic). |
  | CustomerType  | string   | Customer class. |
  | MessageCount  | long     | Metric value (e.g., bytes/messages). |

- Column Explain:
  - MetricName: choose ‘OutboundTraffic’ for egress KPI.

---

### Table name: RPSettingLatest
- Priority: Normal
- What this table represents: Latest resource provisioning settings (SKU, Kind, flags).
- Freshness expectations: Near-latest per resource; exact latency unknown.
- When to use / When to avoid:
  - Use: Enrich usage with SKU, Kind, ServiceMode and flags (e.g., IsPrivateEndpointSet).
  - Avoid: Historical settings; this is latest snapshot only.
- Similar tables & how to choose:
  - None for history; treat as point-in-time snapshot.
- Common Filters:
  - Join on normalized ResourceId (lowercased; no replicas).
- Table columns:

  | Column                 | Type     | Description |
  |------------------------|----------|-------------|
  | ResourceId             | string   | Normalized ARM resource id. |
  | Region                 | string   | Azure region. |
  | SKU                    | string   | Plan. |
  | Kind                   | string   | Service kind. |
  | State                  | string   | Provisioning state. |
  | ServiceMode            | string   | Default/Serverless/etc. |
  | IsUpstreamSet          | bool     | Flag. |
  | IsEventHandlerSet      | bool     | Flag. |
  | EnableTlsClientCert    | bool     | Flag. |
  | IsPrivateEndpointSet   | bool     | Flag. |
  | EnablePublicNetworkAccess | bool  | Flag. |
  | DisableLocalAuth       | bool     | Flag. |
  | DisableAadAuth         | bool     | Flag. |
  | IsServerlessTimeoutSet | bool     | Flag. |
  | AllowAnonymousConnect  | bool     | Flag. |
  | EnableRegionEndpoint   | bool     | Flag. |
  | ResourceStopped        | bool     | Flag. |
  | EnableLiveTrace        | bool     | Flag. |
  | EnableResourceLog      | bool     | Flag. |
  | LastUpdated            | datetime | Last update time. |
  | Extras                 | string   | Additional config. |

- Column Explain:
  - SKU/Kind/ServiceMode: commonly used enrichments in usage queries.

---

### Table name: RuntimeResourceTags_Daily
- Priority: Normal
- What this table represents: Daily tagging/attributes derived from runtime (classification flags).
- Freshness expectations: Daily batch.
- When to use / When to avoid:
  - Use: Tag-based segmentation (AppService/StaticApps/Proxy), success/failure flags.
  - Avoid: Replacing RPSettingLatest; this is runtime-derived.
- Similar tables & how to choose:
  - RPSettingLatest: control plane vs runtime tags.
- Common Filters:
  - Date; ServiceType; ResourceId/SubscriptionId.
- Table columns:

  | Column          | Type     | Description |
  |-----------------|----------|-------------|
  | Date            | datetime | Day. |
  | ResourceId      | string   | ARM resource id. |
  | SubscriptionId  | string   | ARM subscription. |
  | ServiceType     | string   | Product kind. |
  | IsAppService    | bool     | Tag. |
  | IsStaticApps    | bool     | Tag. |
  | IsSample        | bool     | Tag. |
  | IsProxy         | bool     | Tag. |
  | HasFailure      | bool     | Tag. |
  | HasSuccess      | bool     | Tag. |
  | Extra           | string   | Extra attributes. |

- Column Explain:
  - Boolean tags: used for slicing cohorts.

---

### Table name: Cached_SubsTotalWeekly_Snapshot
- Priority: Normal
- What this table represents: Weekly subscription counts snapshot by SKU/segment/service.
- Freshness expectations: Weekly snapshot.
- Table columns: same pattern as Cached_ZnOKRSubsWeekly_Snapshot (see schema there).

---

### Table name: Cached_SubsTotalMonthly_Snapshot
- Priority: Normal
- What this table represents: Monthly subscription counts snapshot by SKU/segment/service.
- Freshness expectations: Monthly snapshot.
- Table columns: same pattern as Cached_ZnOKRSubsMonthly_Snapshot.

---

### Table name: Cached_CustomerFlow_Snapshot
- Priority: Normal
- What this table represents: Snapshot of customer counts by segmentation (category, region, SKU, hasConnection/live ratio).
- Freshness expectations: Snapshot; schedule unknown.
- When to use / When to avoid:
  - Use: Customer cohort sizes across segments.
- Common Filters:
  - Category/Region/SKU/HasConnection/LiveRatio.
- Table columns:

  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Category      | string   | Cohort category. |
  | Region        | string   | Region. |
  | SKU           | string   | Plan. |
  | HasConnection | bool     | Activity flag. |
  | LiveRatio     | string   | Live activity ratio (stringified). |
  | CustomerType  | string   | Segment. |
  | SegmentationType | string| Segmentation. |
  | CustomerCnt   | long     | Customers count. |
  | Date          | datetime | Snapshot date. |
  | ServiceType   | string   | Product. |
  | Partition     | string   | Partition key. |

- Column Explain:
  - CustomerCnt: cohort size; key KPI.

---

### Table name: Cached_ResourceFlow_Snapshot
- Priority: Normal
- What this table represents: Snapshot of resource counts by segmentation.
- Freshness expectations: Snapshot.
- Table columns:

  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Category      | string   | Category. |
  | Region        | string   | Region. |
  | SKU           | string   | Plan. |
  | HasConnection | bool     | Activity flag. |
  | LiveRatio     | string   | Live ratio string. |
  | ResourceCnt   | long     | Resources count. |
  | Date          | datetime | Snapshot date. |
  | ServiceType   | string   | Product. |
  | Partition     | string   | Partition key. |

---

### Table name: ResourceFlow_Weekly (function)
- Priority: Normal
- What this table represents: Weekly resource flow function requiring parameters (e.g., startDate).
- Freshness expectations: Computed; parameterized.
- When to use / When to avoid:
  - Use: Weekly flow analysis with proper parameters.
  - Avoid: Without parameters; prefer cached snapshots.
- Table columns: Not resolvable without parameters. Refer to function definition in the workspace.

---

### Table name: ResourceFlow_Monthly (function)
- Priority: Normal
- Similar to ResourceFlow_Weekly, monthly cadence; parameters required.

---

### Table name: SubscriptionFlow_Weekly (function)
- Priority: Normal
- Weekly subscription flow; parameters required.

---

### Table name: SubscriptionFlow_Monthly (function)
- Priority: Normal
- Monthly subscription flow; parameters required.

---

### Table name: CustomerFlow_Weekly (function)
- Priority: Normal
- Weekly customer flow; parameters required.

---

### Table name: CustomerFlow_Monthly (function)
- Priority: Normal
- Monthly customer flow; parameters required.

---

### Table name: SubscriptionRetentionSnapshot
- Priority: Normal
- What this table represents: Per-subscription retention period window (start/end snapshot).
- Freshness expectations: Snapshot; schedule unknown.
- When to use / When to avoid:
  - Use: Build retention curves by cohort.
- Table columns:

  | Column         | Type     | Description |
  |----------------|----------|-------------|
  | SubscriptionId | string   | Subscription key. |
  | StartDate      | datetime | Retention start. |
  | EndDate        | datetime | Retention end. |

---

### Table name: CustomerRetentionSnapshot
- Priority: Normal
- What this table represents: Per-customer (C360) retention window.
- Table columns:

  | Column   | Type     | Description |
  |----------|----------|-------------|
  | C360_ID  | string   | Customer id. |
  | StartDate| datetime | Start. |
  | EndDate  | datetime | End. |

---

### Table name: ResourceRetentionSnapshot
- Priority: Normal
- What this table represents: Per-resource retention window.
- Table columns:

  | Column    | Type     | Description |
  |-----------|----------|-------------|
  | ResourceId| string   | ARM resource. |
  | StartDate | datetime | Start. |
  | EndDate   | datetime | End. |

---

### Table name: AwpsRetention_SubscriptionSnapshot
- Priority: Normal
- What this table represents: WebPubSub subscription retention window.
- Table columns: same shape as SubscriptionRetentionSnapshot.

  | Column         | Type     | Description |
  |----------------|----------|-------------|
  | SubscriptionId | string   | Subscription key. |
  | StartDate      | datetime | Start. |
  | EndDate        | datetime | End. |

---

### Table name: AwpsRetention_CustomerSnapshot
- Priority: Normal
- What this table represents: WebPubSub customer retention window.
- Table columns: same shape as CustomerRetentionSnapshot.

  | Column   | Type     | Description |
  |----------|----------|-------------|
  | C360_ID  | string   | Customer id. |
  | StartDate| datetime | Start. |
  | EndDate  | datetime | End. |

---

### Table name: AwpsRetention_ResourceSnapshot
- Priority: Normal
- What this table represents: WebPubSub resource retention window.
- Table columns: same shape as ResourceRetentionSnapshot.

  | Column    | Type     | Description |
  |-----------|----------|-------------|
  | ResourceId| string   | ARM resource. |
  | StartDate | datetime | Start. |
  | EndDate   | datetime | End. |

---

### Table name: DeleteSurvey
- Priority: Normal
- What this table represents: User feedback on delete actions (SignalR).
- Freshness expectations: Event-based ingestion.
- When to use / When to avoid:
  - Use: Analyze reasons/feedback on delete.
- Table columns:

  | Column    | Type     | Description |
  |-----------|----------|-------------|
  | TIMESTAMP | datetime | Event time. |
  | Deployment| string   | Environment/deployment slot. |
  | resourceId| string   | ARM resource. |
  | reason    | string   | Reason code. |
  | feedback  | string   | Freeform feedback. |
  | objectId  | string   | AAD object id (if present). |
  | sessionId | string   | Session id. |

---

### Table name: DeleteSurveyWebPubSub
- Priority: Normal
- What this table represents: WebPubSub delete survey; same schema as DeleteSurvey.

---

### Table name: ManageRPQosDaily
- Priority: Normal
- What this table represents: Daily QoS of management plane (RP) operations.
- Freshness expectations: Daily batch.
- When to use / When to avoid:
  - Use: Overall QoS = (Success + Timeout + CustomerError)/Total; counts per API by region.
  - Avoid: Runtime QoS; use OperationQoS_Daily / ConnectivityQoS_Daily.
- Similar tables & how to choose:
  - OperationQoS_Daily/ConnectivityQoS_Daily are runtime metrics.
- Common Filters:
  - Date windows; CustomerType == 'SignalR'; exclude ApiName 'UNCATEGORY'.
  - Restrict ApiName set (e.g., CreateResource, DeleteResource, UpdateResource, MoveResource, CheckNameAvailability).
- Table columns:

  | Column         | Type     | Description |
  |----------------|----------|-------------|
  | Date           | datetime | Day. |
  | ApiName        | string   | Operation name. |
  | SubscriptionId | string   | ARM subscription. |
  | CustomerType   | string   | Customer class. |
  | Region         | string   | Region. |
  | Result         | string   | Success/Timeout/CustomerError/Error. |
  | Count          | long     | Operation count. |

- Column Explain:
  - Result/Count used to compute QoS.

---

### Table name: ErrorsRedis_Hourly
- Priority: Normal
- What this table represents: Hourly Redis error counts across clusters.
- Freshness expectations: Hourly aggregation.
- When to use / When to avoid:
  - Use: Redis incident visibility (ResourceCount, PodCount, ErrorCount by ErrorType).
  - Avoid: Runtime exceptions; use RuntimeExceptions_Hourly.
- Common Filters:
  - DateHour >= startofday(now()) - N days; exclude transient internal (ErrorType filters).
- Table columns:

  | Column    | Type   | Description |
  |-----------|--------|-------------|
  | DateHour  | string | Hour bucket (string). |
  | Cluster   | string | Cluster id; region often last char to drop. |
  | RedisId   | string | Redis instance id. |
  | ResourceId| string | ARM resource. |
  | PodName   | string | Pod name. |
  | ErrorType | string | Error classification. |
  | EventName | string | Event source/name. |
  | ErrorCount| long   | Count. |

- Column Explain:
  - Cluster/Region inference: Region = substring(Cluster, 0, strlen(Cluster)-1) per usage pattern.

---

### Table name: RuntimeExceptions_Hourly
- Priority: Normal
- What this table represents: Hourly runtime exception metrics.
- Freshness expectations: Hourly aggregation.
- When to use / When to avoid:
  - Use: Investigate error hotspots by Logger/ErrorType.
- Table columns:

  | Column     | Type     | Description |
  |------------|----------|-------------|
  | Timestamp  | datetime | Event time. |
  | Cluster    | string   | Cluster. |
  | PodName    | string   | Pod. |
  | ResourceId | string   | ARM resource. |
  | Logger     | string   | Logger name. |
  | ErrorType  | string   | Error type. |
  | ErrorMessage| string  | Details. |
  | Properties | string   | Additional info. |
  | ErrorCount | long     | Count. |

---

### Table name: RPExceptions_Hourly
- Priority: Normal
- What this table represents: Hourly management plane exception counts.
- Freshness expectations: Hourly aggregation.
- Table columns:

  | Column               | Type     | Description |
  |----------------------|----------|-------------|
  | Timestamp            | datetime | Time. |
  | Region               | string   | Region. |
  | ServiceTypeName      | string   | Service type. |
  | RoleInstance         | string   | Instance. |
  | CorrelationRequestId | string   | Correlation id. |
  | ErrorType            | string   | Error type. |
  | ShortMessage         | string   | Short message. |
  | ErrorCount           | long     | Count. |

---

### Table name: ErrorsAbortedConnections_Daily
- Priority: Normal
- What this table represents: Daily aborted connection error metrics.
- Freshness expectations: Daily batch.
- Table columns:

  | Column     | Type     | Description |
  |------------|----------|-------------|
  | Date       | datetime | Day. |
  | Cluster    | string   | Cluster. |
  | ResourceId | string   | ARM resource. |
  | PodName    | string   | Pod. |
  | ServerConnectionCount | long | Server-side connections. |
  | ClientConnectionCount | long | Client-side connections. |

---

### Table name: TopCx_W
- Priority: Normal
- What this table represents: Weekly top customers (schema unresolved here).
- Freshness expectations: Weekly batch; unknown.
- Guidance: Prefer cached “TopCustomersWoW” snapshots; or derive with daily facts + SubscriptionMappings.
- Table columns: Schema not available in this environment.

---

### Table name: OperationQoS_Daily
- Priority: Low
- What this table represents: Runtime availability (operation QoS) per role/region/time (env_* fields).
- Freshness expectations: Daily/hour-level env_time buckets; daily aggregated in queries.
- When to use / When to avoid:
  - Use: QoS = sum(totalUpTimeSec)/sum(totalTimeSec) by env_time/region; compute SLA attainment.
  - Use: Rolling windows by joining last env_time and summing prior N days.
  - Avoid: Connectivity-specific QoS; use ConnectivityQoS_Daily.
- Similar tables & how to choose:
  - ConnectivityQoS_Daily: connectivity QoS; thresholds differ (e.g., 0.995 vs 0.999).
- Common Filters:
  - env_time > ago(Nd); resourceId has 'microsoft.signalrservice/signalr'.
  - Region via env_cloud_location; Sku from env_cloud_deploymentUnit (via joins).
- Table columns:

  | Column                 | Type     | Description |
  |------------------------|----------|-------------|
  | env_name               | string   | Environment name. |
  | env_time               | datetime | Time bucket. |
  | resourceId             | string   | ARM resource id. |
  | env_cloud_role         | string   | Role. |
  | env_cloud_roleInstance | string   | Role instance. |
  | env_cloud_environment  | string   | Cloud environment. |
  | env_cloud_location     | string   | Region. |
  | env_cloud_deploymentUnit| string  | Deployment unit/SKU. |
  | totalUpTimeSec         | long     | Uptime seconds. |
  | totalTimeSec           | long     | Total seconds. |

- Column Explain:
  - env_time: time axis for QoS.
  - totalUpTimeSec/totalTimeSec: used to compute QoS.

---

### Table name: ConnectivityQoS_Daily
- Priority: Low
- What this table represents: Connectivity availability QoS; same schema as OperationQoS_Daily.
- Freshness expectations: Daily/hour-level buckets aggregated in queries.
- When to use / When to avoid:
  - Use: Connectivity QoS and SLA attainment (e.g., threshold 0.995).
  - Avoid: Overall operation QoS; use OperationQoS_Daily.
- Common Filters:
  - env_time windows; resourceId service kind; region via env_cloud_location.
- Table columns: same as OperationQoS_Daily.

---

### Table name: ConnectionQoS_Daily
- Priority: Low
- What this table represents: Daily connection QoS per resource and endpoint.
- Freshness expectations: Daily batch.
- When to use / When to avoid:
  - Use: Compute ServiceQos = 1 - ServiceAbortedConnection/TotalConnection; percentile via tdigest.
  - Avoid: Abort reason distribution; use ConnectionQoSAbortReason_Daily.
- Common Filters:
  - Date > ago(Nd); group by ResourceId.
- Table columns:

  | Column                 | Type     | Description |
  |------------------------|----------|-------------|
  | Date                   | datetime | Day. |
  | ResourceId             | string   | ARM resource. |
  | Endpoint               | string   | Endpoint id. |
  | TotalConnection        | long     | Total connections. |
  | SuccessConnection      | long     | Successful connections. |
  | ServiceAbortedConnection | long   | Service-aborted connections. |

- Column Explain:
  - ServiceAbortedConnection/TotalConnection: inputs to QoS.

---

### Table name: ConnectionQoSAbortReason_Daily
- Priority: Low
- What this table represents: Daily counts of connections aborted by reason.
- Freshness expectations: Daily batch.
- When to use / When to avoid:
  - Use: Drill into abort reasons per resource.
- Table columns:

  | Column       | Type     | Description |
  |--------------|----------|-------------|
  | Date         | datetime | Day. |
  | ResourceId   | string   | ARM resource. |
  | AbortReason  | string   | Reason/category. |
  | ConnectionCount | long  | Count of affected connections. |

---

### Table name: RuntimeRequestsGroups_Daily
- Priority: Low
- What this table represents: Daily grouped runtime requests (category/metrics).
- Freshness expectations: Daily batch.
- Table columns:

  | Column     | Type     | Description |
  |------------|----------|-------------|
  | Date       | datetime | Day. |
  | Category   | string   | Group/category. |
  | Metrics    | string   | Metric name. |
  | ResourceCount | long  | Distinct resources. |
  | RequestCount  | long  | Requests count. |

---

### Table name: RuntimeTransport_Daily
- Priority: Low
- What this table represents: Daily runtime requests split by transport/framework.
- Freshness expectations: Daily batch.
- When to use / When to avoid:
  - Use: Transport share (WebSockets/LongPolling) and framework distribution by feature.
- Common Filters:
  - Date; Feature/Transport/Framework; ResourceId/SubscriptionId.
- Table columns:

  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Date          | datetime | Day. |
  | Feature       | string   | Feature name. |
  | Transport     | string   | Transport (e.g., WebSockets). |
  | Framework     | string   | Client framework. |
  | ResourceId    | string   | ARM resource. |
  | SubscriptionId| string   | ARM subscription. |
  | RequestCount  | long     | Requests. |

---

### Table name: RuntimeTransport_EU_Daily
- Priority: Low
- What this table represents: EU-only RuntimeTransport daily.
- Table columns: same as RuntimeTransport_Daily.

---

### Table name: AwpsRuntimeRequestsGroups_Daily
- Priority: Low
- What this table represents: WebPubSub runtime request groups daily.
- Table columns: same as RuntimeRequestsGroups_Daily.

---

### Table name: WebTools_Raw (cross-source)
- Priority: Low
- Source: cluster("ddtelinsights").database("<DDTEL_DB>")
- What this table represents: Visual Studio WebTools telemetry; dev usage signals referencing SignalR.
- Freshness expectations: Near-real-time event ingestion; queries typically use last 30d.
- When to use / When to avoid:
  - Use: Developer adoption signals (event types/states).
  - Avoid: Service-side operations; billing usage.
- Common Filters:
  - AdvancedServerTimestampUtc >= ago(30d)
  - EventName filters (e.g., 'vs/webtools/servicedependencies/state'); Properties/Measures contains 'signalr'.
- Table columns (inferred from queries):

  | Column                     | Type     | Description |
  |----------------------------|----------|-------------|
  | AdvancedServerTimestampUtc | datetime | Event timestamp. |
  | EventName                  | string   | VS telemetry event. |
  | Properties                 | string   | Key-value payload. |
  | Measures                   | dynamic? | Numeric measures; used via indexing. |
  | ExeVersion                 | string   | VS extension version. |
  | MacAddressHash             | string   | Client hash for dcount. |

- Column Explain:
  - EventName/State derivations for adoption states (Suggested/Missing/Added/etc.).
  - MacAddressHash: unique dev count.

---

### Table name: Requests (cross-source)
- Priority: Low
- Source: cluster("armprodgbl.eastus").database("<ARM_DB>")
- What this table represents: ARM service control plane request logs.
- Freshness expectations: Near-real-time with ingestion delay.
- When to use / When to avoid:
  - Use: Track PUT/DELETE on SIGNALR/EVENTGRIDFILTERS; build add/remove actions.
  - Avoid: Service runtime QoS.
- Common Filters:
  - TIMESTAMP > ago(30d)
  - targetResourceProvider == 'MICROSOFT.SIGNALRSERVICE'
  - httpMethod in ('PUT','DELETE')
  - targetResourceType == 'SIGNALR/EVENTGRIDFILTERS'
  - subscriptionId not in specific exclusion list
- Table columns (inferred from queries):

  | Column                | Type     | Description |
  |-----------------------|----------|-------------|
  | TIMESTAMP             | datetime | Request time. |
  | targetResourceProvider| string   | Provider name. |
  | httpMethod            | string   | HTTP verb. |
  | targetResourceType    | string   | Resource type. |
  | subscriptionId        | string   | ARM subscription. |
  | targetUri             | string   | Target resource URI. |
  | SourceNamespace       | string   | Source (for Location mapping). |

- Column Explain:
  - targetUri: used to parse ResourceId (substring 33..indexof('?')-33).

---

### Table name: HttpIncomingRequests (cross-source)
- Priority: Low
- Source: cluster("armprodgbl.eastus").database("<ARM_DB>")
- What this table represents: Alternate incoming requests log (unioned with Requests).
- Freshness expectations: Near-real-time with ingestion delay.
- Common Filters: same as Requests.
- Table columns: similar to Requests; use Unionizer('Requests','HttpIncomingRequests') in queries to abstract over both.

---

## Additional Low-priority QoS/Operational tables

### Table name: RuntimeACSErrors_Daily
- Priority: Normal
- What this table represents: Daily ACS-related error events (kind/name/reason).
- Table columns:

  | Column   | Type     | Description |
  |----------|----------|-------------|
  | Timestamp| datetime | Event time. |
  | Region   | string   | Region. |
  | Cluster  | string   | Cluster. |
  | Kind     | string   | Error kind. |
  | Name     | string   | Component name. |
  | Reason   | string   | Reason. |
  | Count    | long     | Count. |

---

## Usage patterns and anti-patterns across tables

- Common Filters:
  - Time window: prefer concise windows (e.g., last 28–60 days). Use startofweek/startofmonth for aligned aggregates.
  - Service scoping: Role/ResourceId has 'microsoft.signalrservice/signalr' or '/webpubsub/'. Normalize resource ids tolower() and strip '/replicas'.
  - Exclude internal: SubscriptionId !in (SignalRTeamInternalSubscriptionIds()).
  - Join enrichment: leftouter join RPSettingLatest (on ResourceId) and inner join SubscriptionMappings (on SubscriptionId).
  - Metric-specific: MetricName == 'OutboundTraffic' for egress; ApiName filters for RP QoS; Result in ('Success','Timeout','CustomerError') for QoS numerator.

- When to avoid:
  - Using latest partition of Daily tables for “today” dashboards without acknowledging partial data.
  - Mixing max and sum across weekly rollups incorrectly: for MaxConnectionCount_Daily/AvgConnectionCountEP_Daily, use max for weekly maxima; for SumMessageCount_Daily, use sum for weekly totals.
  - Treating RPSettingLatest as historical; it’s a point-in-time snapshot.

- Similar tables & how to choose:
  - FeatureTrack family: prefer V2; EU variant for region-restricted reporting.
  - QoS family: OperationQoS vs ConnectivityQoS depending on SLA definition/thresholds.
  - Usage metrics: MaxConnectionCount vs AvgConnectionCountEP vs SumMessageCount vs BoundTraffic (egress).
  - Cached_* snapshots vs dynamic functions (TopSubscriptions): prefer cached for performance; switch to dynamic when flexibility is required.

- Revenue computation placeholder:
  - Revenue = case(SKU == 'Free', 0.0, SKU == 'Standard', <UnitPrice_Standard>, SKU == 'Premium', <UnitPrice_Premium>, <UnitPrice_Fallback>) * Quantity
  - For usage-type split: extend UsageType = iif(CustomerType == 'Internal', CustomerType, BillingType)

This playbook captures table roles, schema, and usage conventions observed in the provided queries for SignalR and Web PubSub analytics on cluster signalrinsights.eastus2 (SignalRBI). Where schema was not resolvable (function-backed or cross-cluster tables), guidance and inferred fields were provided from query usage.

## Views (Reusable Layers)
Not applicable. No view definitions were provided in the input. Function-backed entities (e.g., TopSubscriptions, Flow functions) exist but bodies were not provided.

## Query Building Blocks (Copy-paste snippets)

- Time window template with effective end time and completeness gate
```kusto
let StartDate = startofmonth(ago(3mo));
let MinRegions = <MinRegions>;
let EndGate = toscalar(MaxConnectionCount_Daily
    | where Date >= ago(30d)
    | summarize Regions=dcount(Region) by Date
    | where Regions >= MinRegions
    | summarize arg_max(Date, Regions)
    | project Date);
let EffectiveEnd = iff(isnull(EndGate), startofday(ago(1d)), EndGate);
let TimeFilter = (T:(*) ) {
  T
  | where Date between (StartDate .. EffectiveEnd)
  | project-rename TimeCol = Date
};
```

- Service and tenancy filters + resource normalization
```kusto
let IsSignalR = (s:string) { s has "microsoft.signalrservice/signalr" or s has "/signalr/" };
let IsWebPubSub = (s:string) { s has "microsoft.signalrservice/webpubsub" or s has "/webpubsub/" };
let NormalizeRoleToResource = (T:(Role:string)) {
  T
  | extend ResourceId = tolower(iif(Role has "/replicas/", substring(Role, 0, indexof(Role, "/replicas/")), Role))
};
let ExcludeInternal = (T:(SubscriptionId:string)) {
  T | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
};
```

- Join template (facts → dimensions → config)
```kusto
let JoinDimsAndConfig = (F:(SubscriptionId:string, ResourceId:string)) {
  F
  | join kind=inner (SubscriptionMappings | project SubscriptionId, CustomerType, SegmentName, BillingType, CloudCustomerGuid) on SubscriptionId
  | join kind=leftouter (RPSettingLatest | project ResourceId, SKU, Kind, ServiceMode, Region) on ResourceId
  | project-away SubscriptionId1, ResourceId1
};
```

- De-dup pattern (latest per key)
```kusto
RPSettingLatest
| summarize arg_max(LastUpdated, *) by ResourceId
```

- Important filters (defaults)
```kusto
| where IsSignalR(tolower(ResourceId)) or IsWebPubSub(tolower(ResourceId))
| invoke ExcludeInternal()
```

- ID parsing/derivation (ARM control-plane requests → ResourceId)
```kusto
cluster("armprodgbl.eastus").database("<ARM_DB>").Requests
| where TIMESTAMP >= ago(30d)
| where targetResourceProvider == "MICROSOFT.SIGNALRSERVICE"
| where targetResourceType == "SIGNALR/EVENTGRIDFILTERS"
| extend qIndex = indexof(targetUri, "?")
| extend ResourceId = tolower(iif(qIndex > 0, substring(targetUri, 33, qIndex - 33), substring(targetUri, 33)))
| project-rename TimeCol = TIMESTAMP
```

- Sharded/variant union pattern (global + EU feature tracking)
```kusto
let FTGlobal = FeatureTrackV2_Daily | project Date, Feature, Category, ResourceId, SubscriptionId, RequestCount, Partition="Global";
let FTEU     = FeatureTrackV2_EU_Daily | project Date, Feature, Category, ResourceId, SubscriptionId, RequestCount, Partition="EU";
union isfuzzy=true FTGlobal, FTEU
| project-rename TimeCol = Date
| summarize Requests=sum(RequestCount) by Partition, Feature, Category, bin(TimeCol, 7d)
```

- Revenue mapping snippet (placeholder prices)
```kusto
let UnitPrice_Standard = <UnitPrice_Standard>;
let UnitPrice_Premium = <UnitPrice_Premium>;
let UnitPrice_Fallback = <UnitPrice_Fallback>;
let AddRevenue = (T:(SKU:string, Quantity:real)) {
  T
  | extend Revenue = case(
      SKU == "Free", 0.0,
      SKU == "Standard", UnitPrice_Standard,
      SKU == "Premium", UnitPrice_Premium,
      UnitPrice_Fallback) * Quantity
};
```

## Example Queries (with explanations)

1) Monthly estimated revenue by service and SKU from BillingUsage_Daily
Description: Computes monthly revenue using placeholder unit prices, excludes internal subscriptions, and scopes to SignalR/WebPubSub by ResourceId. Adjust StartMonth/MonthsBack and unit prices as needed.
```kusto
let StartMonth = startofmonth(ago(6mo));
let EndMonth = startofmonth(ago(1d)); // avoid current partial month
let UnitPrice_Standard = <UnitPrice_Standard>;
let UnitPrice_Premium = <UnitPrice_Premium>;
let UnitPrice_Fallback = <UnitPrice_Fallback>;
BillingUsage_Daily
| where Date between (StartMonth .. EndMonth)
| where tolower(ResourceId) has "/signalr/" or tolower(ResourceId) has "/webpubsub/"
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
| extend Revenue = case(
    SKU == "Free", 0.0,
    SKU == "Standard", UnitPrice_Standard,
    SKU == "Premium", UnitPrice_Premium,
    UnitPrice_Fallback) * Quantity
| summarize Revenue=sum(Revenue), Quantity=sum(Quantity) by Service=iif(tolower(ResourceId) has "/webpubsub/", "WebPubSub", "SignalR"), SKU, Month=startofmonth(Date)
| order by Month asc, Service asc, SKU asc
```

2) Weekly peak connections by CustomerType and ServiceMode
Description: Normalizes Role to ResourceId, excludes internal subscriptions, joins SubscriptionMappings and RPSettingLatest for enrichment, then computes weekly maxima of daily peaks. Useful for capacity peak tracking by segment and SKU mode.
```kusto
MaxConnectionCount_Daily
| invoke NormalizeRoleToResource()
| where tolower(ResourceId) has "/signalr/" or tolower(ResourceId) has "/webpubsub/"
| invoke ExcludeInternal()
| summarize DailyPeak=max(MaxConnectionCount) by ResourceId, SubscriptionId, CustomerType, Date
| join kind=leftouter (RPSettingLatest | project ResourceId, ServiceMode, SKU, Region) on ResourceId
| summarize WeeklyPeak=max(DailyPeak) by Week=startofweek(Date), CustomerType, ServiceMode, SKU
| order by Week asc
```

3) Weekly total messages by subscription (top 20)
Description: Aggregates message volume weekly, excludes internal subscriptions, and ranks top 20 subscriptions per week. Adapt time window and ranking size via N.
```kusto
let N = 20;
SumMessageCount_Daily
| invoke NormalizeRoleToResource()
| where tolower(ResourceId) has "/signalr/" or tolower(ResourceId) has "/webpubsub/"
| invoke ExcludeInternal()
| summarize WeeklyMessages=sum(MessageCount) by Week=startofweek(Date), SubscriptionId
| extend rn = row_number(Week, desc, WeeklyMessages) // per week ranking
| where rn <= N
| order by Week asc, WeeklyMessages desc
```

4) EU feature adoption trend by feature (weekly)
Description: Uses FeatureTrackV2_EU_Daily to plot weekly request counts for selected features. Modify Features list or switch to global table for worldwide views.
```kusto
let Features = dynamic(["negotiate", "sendToAll", "sendToGroup"]);
FeatureTrackV2_EU_Daily
| where Date >= ago(90d)
| where Feature in (Features)
| summarize Requests=sum(RequestCount) by Feature, Week=startofweek(Date)
| order by Week asc, Feature asc
```

5) Outbound traffic KPI (WebPubSub) by week and region
Description: Filters BoundTraffic_Daily to OutboundTraffic metric, normalizes resource, excludes internal subscriptions, and sums weekly egress by region. Adjust time window as needed.
```kusto
BoundTraffic_Daily
| where Date >= ago(60d)
| where MetricName == "OutboundTraffic"
| invoke NormalizeRoleToResource()
| where tolower(ResourceId) has "/webpubsub/"
| invoke ExcludeInternal()
| summarize WeeklyOutbound=sum(MessageCount) by Region, Week=startofweek(Date)
| order by Week asc, Region asc
```

6) Management RP QoS by API and region (weekly)
Description: Computes QoS as (Success+Timeout+CustomerError)/Total for selected APIs. Excludes “UNCATEGORY” and restricts to SignalR RP rows. Adjust API list and time horizon.
```kusto
let InterestingApis = dynamic(["CreateResource","DeleteResource","UpdateResource","MoveResource","CheckNameAvailability"]);
ManageRPQosDaily
| where Date >= ago(60d)
| where CustomerType == "SignalR"
| where ApiName in (InterestingApis) and ApiName != "UNCATEGORY"
| summarize Total=sum(Count), Good=sum(iif(Result in ("Success","Timeout","CustomerError"), Count, 0)) by ApiName, Region, Week=startofweek(Date)
| extend QoS = todouble(Good) / todouble(Total)
| order by Week asc, ApiName asc, Region asc
```

7) Connection QoS percentiles across resources
Description: Computes per-resource daily service QoS and then weekly distribution percentiles (P50/P95/P99). Useful for SLA attainment distribution views. Modify thresholds or groupings as needed.
```kusto
ConnectionQoS_Daily
| where Date >= ago(60d)
| extend ServiceQos = 1.0 - todouble(ServiceAbortedConnection) / todouble(max_of(1, TotalConnection))
| summarize DailyQos=avg(ServiceQos) by ResourceId, Week=startofweek(Date)
| summarize P50=percentile(DailyQos, 50), P95=percentile(DailyQos, 95), P99=percentile(DailyQos, 99) by Week
| order by Week asc
```

8) Top subscriptions snapshot (cached) for SignalR vs WebPubSub
Description: Uses Cached_TopSubscriptions_Snapshot to fetch top revenue and message leaders in the cached window. Good for dashboards; switch to direct fact computation for flexible windows.
```kusto
let Svc = "SignalR"; // or "WebPubSub"
Cached_TopSubscriptions_Snapshot
| where Service == Svc
| project SubscriptionId, Revenue, MaxConnection, MessageCount, StartDate, EndDate
| order by Revenue desc
| take 20
```

9) Cross-cluster ARM: add/remove EventGrid filters by subscription (last 30d)
Description: Unions Requests and HttpIncomingRequests, parses ResourceId from targetUri, filters SignalR provider and EVENTGRIDFILTERS type, then computes PUT vs DELETE counts by subscription. Use to see control-plane changes.
```kusto
let Arm = cluster("armprodgbl.eastus").database("<ARM_DB>");
union Arm.Requests, Arm.HttpIncomingRequests
| where TIMESTAMP >= ago(30d)
| where targetResourceProvider == "MICROSOFT.SIGNALRSERVICE"
| where targetResourceType == "SIGNALR/EVENTGRIDFILTERS"
| extend qIndex = indexof(targetUri, "?")
| extend ResourceId = tolower(iif(qIndex > 0, substring(targetUri, 33, qIndex - 33), substring(targetUri, 33)))
| summarize PUT=sum(toint(httpMethod == "PUT")), DELETE=sum(toint(httpMethod == "DELETE")) by SubscriptionId, Day=startofday(TIMESTAMP)
| order by Day desc
```

10) Redis errors hourly: region derivation from cluster name
Description: Demonstrates DateHour parsing and region derivation using substring of Cluster. Adapt filters for ErrorType and time range.
```kusto
ErrorsRedis_Hourly
| where todatetime(DateHour) >= ago(3d)
| extend TimeCol = todatetime(DateHour)
| extend Region = substring(Cluster, 0, strlen(Cluster)-1)
| summarize ErrorCount=sum(ErrorCount), PodCount=dcount(PodName), ResourceCount=dcount(ResourceId) by ErrorType, Region, bin(TimeCol, 1h)
| order by TimeCol asc, ErrorCount desc
```

## Reasoning Notes (only if uncertain)
- Timezone: Not specified. Adopt UTC assumptions to avoid ambiguity but verify if downstream systems require a specific timezone.
- “Active” definitions: Not explicitly defined. Plausible interpretations include:
  1) Any record present within the window.
  2) MaxConnectionCount > 0 within the window.
  3) SumMessageCount > 0 within the window.
  4) OutboundTraffic > 0 (WebPubSub-specific).
  5) FeatureTrackV2 RequestCount > 0 for selected features.
  6) Presence in Cached_* snapshots as a proxy for activity.
  7) Non-zero ConnectionQoS totals.
  8) Resource with ServiceMode == "Default" or specific SKUs.
  9) RuntimeResourceTags_Daily.HasSuccess == true.
  10) RPSettingLatest.State indicates Running/Provisioned.
  Chosen for general reporting: (2) or (3) depending on KPI context; validate with metric owners.
- Completeness gate: Region count threshold is unknown. Use <MinRegions> placeholder; tune against historical distributions.
- Price mapping: No unit prices provided. Use placeholders and centralize in a let block or external function to avoid drift.
- Top subscriptions: Function and trends schemas not provided. When unavailable, derive top-N from BillingUsage_Daily, MaxConnectionCount_Daily, and SumMessageCount_Daily with consistent time windows.
