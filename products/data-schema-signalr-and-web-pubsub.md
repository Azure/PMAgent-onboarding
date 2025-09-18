# SignalR and Web PubSub - Product and Data Overview Template

## 1. Product Overview

Draft: SignalR and Web PubSub provide real-time messaging services with daily fact tables for billing usage, connections, and messages; snapshot dimensions for resource and subscription enrichment; and QoS tables for operational and connectivity availability. The dataset also includes hourly operational error telemetry and cross-cluster ARM/Web Tools telemetry to correlate platform changes and developer adoption.

## 2. Data Platform Overview

- Data Storage: Azure Data Explorer (ADX)
- Product:
  SignalR and Web PubSub
- Product Nick Names: 
  [TODO]Data_Engineer: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations.
- Kusto Cluster:
  signalrinsights.eastus2
- Kusto Database:
  SignalRBI
- Access Control:
  [TODO] Data Engineer: If this product’s data has high confidentiality concerns, please specify the allowed groups/users here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

## Overview
Product: SignalR and Web PubSub

Summary: SignalR and Web PubSub provide real-time messaging services with daily fact tables for billing usage, connections, and messages; snapshot dimensions for resource and subscription enrichment; and QoS tables for operational and connectivity availability. The dataset also includes hourly operational error telemetry and cross-cluster ARM/Web Tools telemetry to correlate platform changes and developer adoption.

Primary cluster and database:
- Cluster: signalrinsights.eastus2
- Database: SignalRBI
- Alternates: Some tables are queried cross-cluster via cluster("ddtelinsights") and cluster("armprodgbl.eastus") with <DB> placeholders.

Timezone and refresh delays: unknown. Be careful with current-day data (daily tables may be partially ingested). Prefer complete prior days/weeks/months unless you explicitly need intraday trends.

## Conventions & Assumptions
- Time semantics
  - Observed timestamp/date columns:
    - Date (datetime) for daily facts
    - env_time (datetime) for QoS daily
    - Timestamp (datetime) and DateHour (string) for hourly errors
    - TIMESTAMP (datetime) for ARM requests
    - AdvancedServerTimestampUtc (datetime) for Web Tools telemetry
  - Canonical Time Column: TimeCol
    - Normalize via project-rename or extend before union/join:
      - Daily facts: | project-rename TimeCol = Date
      - QoS daily: | project-rename TimeCol = env_time
      - Hourly exceptions: | project-rename TimeCol = Timestamp
      - Hourly Redis: | extend TimeCol = todatetime(DateHour)
      - ARM requests: | project-rename TimeCol = TIMESTAMP
      - Web Tools: | project-rename TimeCol = AdvancedServerTimestampUtc
  - Typical time windows:
    - Ago-style: ago(7d), ago(30d)
    - Monthly: startofmonth(now(), -12) to startofmonth(now())
    - Weekly: startofweek(now(), -26) to startofweek(now())
  - Common binning/resolution:
    - Day: bin(TimeCol, 1d) or use Date directly
    - Week: startofweek(Date)
    - Month: startofmonth(Date)
  - Timezone: unknown; assume UTC by default.

- Freshness & Completeness Gates
  - Daily fact tables (BillingUsage_Daily, MaxConnectionCount_Daily, SumMessageCount_Daily, AvgConnectionCountEP_Daily, BoundTraffic_Daily) are populated daily with unknown ingestion delay. Avoid using current day for finalized reporting.
  - Simple effective end-time guard:
    - let EffectiveEnd = startofday(now()); use Date < EffectiveEnd.
  - Multi-slice completeness gate pattern (recommendation):
    - Compute the last day where ≥N sentinel slices (e.g., Regions or Services) report data, then restrict analyses to ≤ that day.

    kusto
    let Services = dynamic(["microsoft.signalrservice/signalr","microsoft.signalrservice/webpubsub"]);
    let MinSlices = 5; // tune by expectation
    let LastCompleteDay =
        toscalar(
            union isfuzzy=true
                (MaxConnectionCount_Daily | extend Service = iif(Role has "webpubsub", "microsoft.signalrservice/webpubsub", "microsoft.signalrservice/signalr")
                                         | where array_index_of(Services, Service) != -1
                                         | summarize Slices=dcount(Region) by Date
                ),
                (SumMessageCount_Daily | extend Service = iif(Role has "webpubsub", "microsoft.signalrservice/webpubsub", "microsoft.signalrservice/signalr")
                                        | where array_index_of(Services, Service) != -1
                                        | summarize Slices=dcount(Region) by Date
                )
            | summarize TotalSlices = sum(Slices) by Date
            | where TotalSlices >= MinSlices
            | top 1 by Date desc
            | project Date
        );
    // Use: | where Date <= LastCompleteDay

- Joins & Alignment
  - Frequent keys:
    - ResourceId (normalize from Role)
    - SubscriptionId
    - Region
    - Customer/CloudCustomerGuid via SubscriptionMappings
  - Normalizing Role to ResourceId (lowercase, trim replicas):
    - extend ResourceId = iif(Role has "replicas", tolower(substring(Role, 0, indexof(Role, "/replicas/"))), tolower(Role))
  - Typical join kinds:
    - join kind=inner SubscriptionMappings on SubscriptionId (to exclude internal cohorts and segment by CustomerType/BillingType)
    - join kind=leftouter RPSettingLatest on ResourceId (annotate kind/SKU/mode)
  - Post-join hygiene:
    - Resolve column name conflicts: project-rename or prefix dimensions; coalesce() if overlapping semantics
    - Drop unused columns: project-away

- Filters & Idioms
  - Resource scoping:
    - Role/resourceId has "microsoft.signalrservice/signalr"
    - Role/resourceId has "microsoft.signalrservice/webpubsub"
  - Cohort filters:
    - Exclude internal subscriptions: | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
    - Build allowlists/denylists via materialized lists and join kind=inner/anti
  - String operators:
    - has for tokenized substring (recommended for ARM ids), contains for general substring; case-insensitive by default
  - Weekly aggregation:
    - For “Max” style metrics: weekly max over daily sums
    - For “Sum” style metrics: weekly sum over daily sums

- Cross-cluster/DB & Sharding
  - Cross-cluster sources:
    - cluster("ddtelinsights").database("<DB>").WebTools_Raw
    - cluster("armprodgbl.eastus").database("<DB>").Requests / HttpIncomingRequests
  - Qualification and union pattern:
    - Use cluster()/database() qualifiers
    - For same-schema shards (e.g., RuntimeTransport_Daily vs RuntimeTransport_EU_Daily): union → normalize keys/time → summarize

    kusto
    union isfuzzy=true RuntimeTransport_Daily, RuntimeTransport_EU_Daily
    | project-rename TimeCol = Date
    | summarize Requests = sum(RequestCount) by TimeCol, Feature, Transport, Framework

- Table classes
  - Fact (daily/events): BillingUsage_Daily, MaxConnectionCount_Daily, SumMessageCount_Daily, AvgConnectionCountEP_Daily, BoundTraffic_Daily, OperationQoS_Daily, ConnectivityQoS_Daily, ConnectionQoS_Daily, ConnectionQoSAbortReason_Daily, ManageRPQosDaily, RuntimeTransport_Daily, RuntimeTransport_EU_Daily, ErrorsRedis_Hourly, RuntimeExceptions_Hourly, RPExceptions_Hourly, RuntimeACSErrors_Daily, RuntimeRequestsGroups_Daily, AwpsRuntimeRequestsGroups_Daily
  - Snapshot (latest state): RPSettingLatest, Cached_TopSubscriptions_Snapshot
  - Pre-aggregated/cached: Cached_* tables; use to seed top cohorts, not for comprehensive counts

## Entity & Counting Rules (Core Definitions)
- Entity model
  - Resource (ResourceId)
    - Unique per ARM resource; normalize Role to base ResourceId for metrics that log at instance/replica granularity
  - Subscription (SubscriptionId)
    - Parent of resources; join to SubscriptionMappings for segmentation
  - Customer (CloudCustomerGuid via SubscriptionMappings)
    - Use for deduplicated customer counts and cohorting
  - Region (Region or env_cloud_location)
    - Optional slice; used for regional KPIs

- Standard grouping levels
  - Resource-level: when diagnosing or ranking specific resources
  - Subscription-level: commercial segmentation and top accounts
  - Customer-level: dedup across subscriptions
  - Region-level: availability and capacity planning views
  - Time-level: day → week (startofweek) → month (startofmonth)

- Business definitions
  - QoS (Operation/Connectivity):
    - QoS = iif(sum(totalTimeSec) == 0, 1.0, 1.0 * sum(totalUpTimeSec) / sum(totalTimeSec))
    - SLA attainment: share of resources with QoS ≥ <QoS_Threshold> (e.g., 0.995/0.999); parameterize threshold
  - Service QoS (Connection-level):
    - ServiceQos = 1.0 - sum(ServiceAbortedConnection) / sum(TotalConnection)
  - Pricing/revenue:
    - Revenue = Quantity * UnitPrice(SKU); use placeholders like <UnitPrice_Standard>, <UnitPrice_Premium>
  - Apply definitions only when explicitly relevant; do not default QoS or revenue unless requested.

## Canonical Tables
## Canonical Table

This playbook is based on the following product context:
- Product: SignalR and Web PubSub
- Cluster: signalrinsights.eastus2
- Database: SignalRBI
- Queries: 120
- Timezone and refresh delays: unknown. Be careful with current-day data (daily tables may be partially ingested). Prefer complete prior days/weeks/months unless you explicitly need intraday trends.

Conventions observed in queries:
- Resource scoping: filter Role/resourceId by strings like 'microsoft.signalrservice/signalr' or 'microsoft.signalrservice/webpubsub'. For Role that includes “/replicas/…”, normalize to the base resourceId using substring before “/replicas/”.
- Tenant scoping: exclude internal subscriptions via SignalRTeamInternalSubscriptionIds (function) when counting customers or revenue.
- Join pattern: enrich metrics with RPSettingLatest (by ResourceId) and SubscriptionMappings (by SubscriptionId).
- Aggregations:
  - Daily facts often re-aggregated to weekly using startofweek(Date).
  - Max semantics: weekly max over daily sums for “MaxConnectionCount” and “AvgConnectionCount”.
  - Sum semantics: weekly sum for message counts and traffic.
- QoS formula: sum(totalUpTimeSec)/sum(totalTimeSec), with a guard iif(sum(totalTimeSec)==0, 1.0, …). SLA attainment uses percentile/threshold checks over resources (thresholds like 0.995 or 0.999 appear; parameterize as needed).
- Pricing in queries: revenue = Quantity * unit price based on SKU. Use placeholders like <UnitPrice_Standard>, <UnitPrice_Premium>.

Below are the core tables used by the product queries. For cross-source tables, the cluster is shown; database is not specified in the input—use a placeholder.

---

- Table name: BillingUsage_Daily
- Priority: High
- What this table represents: Daily billing usage facts per resource and subscription for SignalR/Web PubSub. Fact table; zero rows for a day imply no recorded billable usage that day.
- Freshness expectations: Daily. Exact refresh delay/ingest window unknown; avoid using the current day for final numbers.
- When to use:
  - Monthly revenue/usage rollups by SKU, billing type, customer type.
  - Top subscriptions/resources by paid units or revenue.
  - Cross-check active usage vs. connection/message metrics.
- When to avoid:
  - Sub-daily analysis (it’s daily grain).
  - Operational QoS analysis (use QoS tables instead).
- Similar tables & how to choose:
  - Use MaxConnectionCount_Daily or SumMessageCount_Daily for real-time usage signals; use BillingUsage_Daily for billable consumption and SKU-based revenue.
- Common Filters:
  - Date range (startofmonth/ago).
  - ResourceId contains '/signalr/' or '/webpubsub/'.
  - Exclude internal subscriptions: SubscriptionId !in (SignalRTeamInternalSubscriptionIds).
  - Join SubscriptionMappings for CustomerType/BillingType.
- Table columns:

  | Column | Type | Description or meaning |
  |---|---|---|
  | Date | datetime | Usage date (day grain). |
  | Region | string | Azure region of the resource. |
  | SubscriptionId | string | Azure subscription GUID. |
  | ResourceId | string | Full ARM resourceId. |
  | SKU | string | SKU tier (e.g., Free, Standard, Premium). |
  | Quantity | real | Billed quantity for the day (unit depends on SKU). |

- Column Explain:
  - Date: time filter and month bucketing (startofmonth).
  - SKU: drives revenue multipliers; aggregate by SKU for segmentation.
  - Quantity: core fact for usage and revenue calculations.
  - SubscriptionId/ResourceId: joins to SubscriptionMappings; use to group by customers/resources.
  - Region: used for region-level rollups.

Example revenue rollup (use placeholders for prices):
```kusto
BillingUsage_Daily
| where Date >= startofmonth(now(), -12) and ResourceId has "/signalr/"
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds)
| extend UnitPrice =
    case(SKU == "Free", 0.0,
         SKU == "Standard", <UnitPrice_Standard>,
         SKU == "Premium", <UnitPrice_Premium>, 0.0)
| extend Revenue = UnitPrice * Quantity
| join kind=inner SubscriptionMappings on SubscriptionId
| summarize Revenue = sum(Revenue) by Month = startofmonth(Date), SKU, CustomerType, BillingType
```

---

- Table name: MaxConnectionCount_Daily
- Priority: High
- What this table represents: Daily maximum concurrent connections per resource/subscription. Fact table at day level.
- Freshness expectations: Daily. Exact latency unknown.
- When to use:
  - Trend the peak concurrent connections (daily/weekly).
  - Segment by ServiceMode/Kind/BillingType via joins.
  - Identify top subscriptions/resources by connection peak.
- When to avoid:
  - Average utilization across time (use AvgConnectionCountEP_Daily).
  - Message volume analysis (use SumMessageCount_Daily).
- Similar tables & how to choose:
  - AvgConnectionCountEP_Daily (average connections by endpoint) vs. MaxConnectionCount_Daily (peak).
- Common Filters:
  - Role has '/signalr/' or '/webpubsub/'.
  - Date ranges; weekly rollups via startofweek(Date).
  - Join RPSettingLatest (by ResourceId) and SubscriptionMappings (by SubscriptionId).
- Table columns:

  | Column | Type | Description or meaning |
  |---|---|---|
  | Date | datetime | Day of measurement. |
  | Role | string | ResourceId or instance path (may include '/replicas/…'). |
  | SubscriptionId | string | Subscription GUID. |
  | CustomerType | string | Internal/External classification. |
  | Region | string | Resource region. |
  | MaxConnectionCount | long | Peak concurrent connections that day. |

- Column Explain:
  - Role: normalize to ResourceId by trimming '/replicas/…' for joins.
  - MaxConnectionCount: primary metric to max/sum; for weekly show max of daily sums.

Weekly max (SignalR):
```kusto
let label = "microsoft.signalrservice/signalr";
MaxConnectionCount_Daily
| where Date >= startofweek(now(), -26) and Date < startofweek(now()) and Role has label
| extend ResourceId = iif(Role has "replicas", tolower(substring(Role, 0, indexof(Role, "/replicas/"))), tolower(Role))
| join kind=leftouter (RPSettingLatest | extend ResourceId = tolower(ResourceId)) on ResourceId
| join kind=inner SubscriptionMappings on SubscriptionId
| summarize SumValue = sum(MaxConnectionCount) by Date, CustomerType=CustomerType1, ServiceMode, BillingType
| summarize Value = max(SumValue) by Week=startofweek(Date), CustomerType, ServiceMode, BillingType
```

---

- Table name: SumMessageCount_Daily
- Priority: High
- What this table represents: Daily message counts per resource and subscription. Fact table at day level.
- Freshness expectations: Daily; latency unknown.
- When to use:
  - Aggregate message volume by customer/region/SKU.
  - Correlate with connections and billing.
- When to avoid:
  - Connection concurrency (use Max/Avg connection tables).
- Similar tables & how to choose:
  - BoundTraffic_Daily for traffic volume in bytes vs. message counts here.
- Common Filters:
  - Role has '/signalr/' or '/webpubsub/'.
  - Date ranges; weekly sums.
  - RPSettingLatest and SubscriptionMappings joins.
- Table columns:

  | Column | Type | Description or meaning |
  |---|---|---|
  | Date | datetime | Day. |
  | Role | string | ResourceId or instance path. |
  | Region | string | Region. |
  | SubscriptionId | string | Subscription GUID. |
  | CustomerType | string | Customer classification. |
  | MessageCount | long | Total messages that day. |

- Column Explain:
  - MessageCount: sum across Date to weekly/monthly totals.
  - Role/SubscriptionId: join keys for enrichment.

---

- Table name: AvgConnectionCountEP_Daily
- Priority: Normal
- What this table represents: Daily average connection counts, by endpoint where available.
- Freshness expectations: Daily; latency unknown.
- When to use:
  - Average utilization over time (complements MaxConnectionCount_Daily).
  - Endpoint-level analysis when Endpoint is present.
- When to avoid:
  - Peak capacity reporting (use MaxConnectionCount_Daily).
- Similar tables & how to choose:
  - Use MaxConnectionCount_Daily for peaks; AvgConnectionCountEP_Daily for utilization.
- Common Filters:
  - Role has service label; weekly max of daily averages in examples.
  - Joins to RPSettingLatest and SubscriptionMappings.
- Table columns:

  | Column | Type | Description or meaning |
  |---|---|---|
  | Date | datetime | Day. |
  | Role | string | ResourceId or instance path. |
  | SubscriptionId | string | Subscription GUID. |
  | CustomerType | string | Customer classification. |
  | Region | string | Region. |
  | Endpoint | string | Endpoint dimension (when available). |
  | AvgConnectionCount | long | Average connections that day. |

- Column Explain:
  - AvgConnectionCount: aggregate to weekly via max over daily sums in examples.
  - Endpoint: segment for EP-level insights.

---

- Table name: BoundTraffic_Daily
- Priority: Normal
- What this table represents: Daily traffic counts (e.g., OutboundTraffic) by resource/endpoint.
- Freshness expectations: Daily; latency unknown.
- When to use:
  - Outbound traffic trends for Web PubSub.
  - Billing usage proxy when correlating with message counts.
- When to avoid:
  - Connection-centric KPIs (use connection tables).
- Similar tables & how to choose:
  - SumMessageCount_Daily for message volume; BoundTraffic_Daily for byte traffic.
- Common Filters:
  - MetricName == 'OutboundTraffic'
  - Role has '/webpubsub/'
  - Joins with RPSettingLatest and SubscriptionMappings.
- Table columns:

  | Column | Type | Description or meaning |
  |---|---|---|
  | Date | datetime | Day. |
  | Role | string | ResourceId or instance path. |
  | Region | string | Region. |
  | SubscriptionId | string | Subscription GUID. |
  | Endpoint | string | Endpoint name/path. |
  | MetricName | string | Metric identifier (e.g., OutboundTraffic). |
  | CustomerType | string | Customer classification. |
  | MessageCount | long | Count for the metric (naming inherited; represents metric units). |

- Column Explain:
  - MetricName: choose OutboundTraffic for examples shown.
  - MessageCount: numeric value of the chosen metric for the day.

---

- Table name: SubscriptionMappings
- Priority: High
- What this table represents: Subscription-to-customer enrichment mapping (segment, offer, billing type, etc.). Snapshot-like dimension table.
- Freshness expectations: Updated as customer metadata changes. Exact cadence unknown.
- When to use:
  - Enrich metrics with CustomerType/BillingType/CloudCustomerGuid.
  - Segment by Offer/SegmentName/WorkloadType.
- When to avoid:
  - Direct numeric aggregations (no facts here).
- Similar tables & how to choose:
  - CustomerModel has broader customer attributes; use SubscriptionMappings when the join key is SubscriptionId.
- Common Filters:
  - Join key SubscriptionId to fact tables.
- Table columns:

  | Column | Type | Description or meaning |
  |---|---|---|
  | P360_ID | string | Internal P360 customer id. |
  | CloudCustomerGuid | string | Customer GUID. |
  | SubscriptionId | string | Subscription GUID (join key). |
  | CustomerType | string | Internal/External etc. |
  | CustomerName | string | Display name. |
  | SegmentName | string | Segment/industry/size. |
  | OfferType | string | Offer type code. |
  | OfferName | string | Offer name. |
  | BillingType | string | e.g., EA/Direct/PAYG. |
  | WorkloadType | string | Workload classification. |
  | S500 | string | Additional classification. |

- Column Explain:
  - SubscriptionId: primary join key for enrichment.
  - CustomerType/BillingType: common aggregation dimensions.
  - CloudCustomerGuid: use for deduped customer counts.

---

- Table name: RPSettingLatest
- Priority: Normal
- What this table represents: Latest RP (resource provider) runtime/resource settings per resource. Snapshot per resource.
- Freshness expectations: Updated as settings change; LastUpdated column indicates timestamp. Latency unknown.
- When to use:
  - Enrich resources with Kind, SKU, ServiceMode and feature flags (e.g., Private Endpoint, TLS client cert).
- When to avoid:
  - Historical settings over time (this is “latest” snapshot).
- Similar tables & how to choose:
  - Use with daily fact tables to annotate resource configuration at analysis time.
- Common Filters:
  - Join on normalized ResourceId (lowercase and trim '/replicas').
- Table columns:

  | Column | Type | Description or meaning |
  |---|---|---|
  | ResourceId | string | ARM resource id (join key). |
  | Region | string | Region. |
  | SKU | string | SKU tier. |
  | Kind | string | Service kind (SignalR/WebPubSub). |
  | State | string | Resource state. |
  | ServiceMode | string | Default/Serverless/etc. |
  | IsUpstreamSet | bool | Upstream configured. |
  | IsEventHandlerSet | bool | Event handler configured. |
  | EnableTlsClientCert | bool | TLS client cert enabled. |
  | IsPrivateEndpointSet | bool | Private endpoint configured. |
  | EnablePublicNetworkAccess | bool | PNA enabled. |
  | DisableLocalAuth | bool | Local auth disabled. |
  | DisableAadAuth | bool | AAD disabled. |
  | IsServerlessTimeoutSet | bool | Serverless timeout configured. |
  | AllowAnonymousConnect | bool | Anonymous connect allowed. |
  | EnableRegionEndpoint | bool | Region endpoint enabled. |
  | ResourceStopped | bool | Resource stopped. |
  | EnableLiveTrace | bool | Live trace enabled. |
  | EnableResourceLog | bool | Resource logs enabled. |
  | LastUpdated | datetime | Last update time. |
  | Extras | string | Additional json/flags. |

- Column Explain:
  - ResourceId: join target for enrichment.
  - Kind/ServiceMode/SKU: used in segmentation and cross-service analyses.

---

- Table name: OperationQoS_Daily
- Priority: Low
- What this table represents: Daily operation availability for service instances/resources (service uptime by total time).
- Freshness expectations: Daily; latency unknown.
- When to use:
  - Daily/weekly/monthly QoS trend and SLA attainment by region or overall.
  - Rolling windows (7/28 days) via latest date anchor.
- When to avoid:
  - Connectivity-only QoS (use ConnectivityQoS_Daily).
- Similar tables & how to choose:
  - ConnectivityQoS_Daily for connectivity path; ConnectionQoS_Daily for connection-level outcomes.
- Common Filters:
  - env_time windows via ago/startofweek/startofmonth.
  - resourceId contains 'microsoft.signalrservice/signalr'.
  - Region dimension env_cloud_location.
- Table columns:

  | Column | Type | Description or meaning |
  |---|---|---|
  | env_name | string | Environment name. |
  | env_time | datetime | Day. |
  | resourceId | string | Resource id. |
  | env_cloud_role | string | Cloud role. |
  | env_cloud_roleInstance | string | Instance. |
  | env_cloud_environment | string | Cloud env. |
  | env_cloud_location | string | Region. |
  | env_cloud_deploymentUnit | string | Deployment unit/SKU proxy. |
  | totalUpTimeSec | long | Available seconds. |
  | totalTimeSec | long | Total seconds. |

- Column Explain:
  - totalUpTimeSec/totalTimeSec: compute QoS ratio and SLA attainment.
  - env_time: time bin for grouping and rolling windows.

Weekly/Overall example:
```kusto
OperationQoS_Daily
| where env_time > startofweek(now(), -8) and resourceId has "microsoft.signalrservice/signalr"
| summarize Qos = iif(sum(totalTimeSec)==0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec)),
          UpTime = sum(totalUpTimeSec), TotalTime = sum(totalTimeSec)
  by StartWeek = startofweek(env_time), Region = env_cloud_location, ResourceId = env_cloud_role
| summarize TotalOperation = sum(TotalTime),
          Qos = iif(sum(TotalTime)==0, 1.0, 1.0*sum(UpTime)/sum(TotalTime)),
          SlaAttainment = 1.0 * dcountif(ResourceId, Qos >= <QoS_Threshold>, 4) / dcount(ResourceId, 4)
  by StartWeek, Region
```

---

- Table name: ConnectivityQoS_Daily
- Priority: Low
- What this table represents: Daily connectivity path availability.
- Freshness expectations: Daily; latency unknown.
- When to use:
  - Connectivity QoS trend and SLA attainment.
  - Rolling windows as with OperationQoS_Daily.
- When to avoid:
  - Operation-level availability (use OperationQoS_Daily).
- Similar tables & how to choose:
  - OperationQoS_Daily vs. ConnectivityQoS_Daily—pick based on KPI definition.
- Common Filters:
  - Same as OperationQoS_Daily; resourceId scope and region.
- Table columns:

  | Column | Type | Description or meaning |
  |---|---|---|
  | env_name | string | Environment. |
  | env_time | datetime | Day. |
  | resourceId | string | Resource. |
  | env_cloud_role | string | Role. |
  | env_cloud_roleInstance | string | Instance. |
  | env_cloud_environment | string | Cloud. |
  | env_cloud_location | string | Region. |
  | env_cloud_deploymentUnit | string | Deployment unit. |
  | totalUpTimeSec | long | Available seconds. |
  | totalTimeSec | long | Total seconds. |

- Column Explain:
  - Same QoS formula and grouping as OperationQoS_Daily; use different SLA threshold as needed.

---

- Table name: ConnectionQoS_Daily
- Priority: Low
- What this table represents: Daily connection-level outcomes per resource and endpoint.
- Freshness expectations: Daily; latency unknown.
- When to use:
  - Service QoS as 1 - ServiceAbortedConnection / TotalConnection.
  - Compute percentiles via tdigest for PR metrics.
- When to avoid:
  - Overall availability time-based metrics (use Operation/Connectivity QoS).
- Similar tables & how to choose:
  - ConnectionQoSAbortReason_Daily for abort reason breakdowns.
- Common Filters:
  - Date windows; by ResourceId.
- Table columns:

  | Column | Type | Description or meaning |
  |---|---|---|
  | Date | datetime | Day. |
  | ResourceId | string | Resource id. |
  | Endpoint | string | Endpoint. |
  | TotalConnection | long | Total connections. |
  | SuccessConnection | long | Successful connections. |
  | ServiceAbortedConnection | long | Service-aborted connections. |

- Column Explain:
  - Use ServiceQos = 1 - sum(ServiceAbortedConnection)/sum(TotalConnection).
  - Summarize then build tdigest for percentiles.

---

- Table name: ConnectionQoSAbortReason_Daily
- Priority: Low
- What this table represents: Daily connection aborts by reason per resource.
- Freshness expectations: Daily; latency unknown.
- When to use:
  - Break down connection failures by AbortReason.
- When to avoid:
  - Aggregate QoS (use ConnectionQoS_Daily).
- Similar tables & how to choose:
  - Pair with ConnectionQoS_Daily to quantify impact drivers.
- Common Filters:
  - Date windows; by ResourceId; group by AbortReason.
- Table columns:

  | Column | Type | Description or meaning |
  |---|---|---|
  | Date | datetime | Day. |
  | ResourceId | string | Resource id. |
  | AbortReason | string | Reason category. |
  | ConnectionCount | long | Connections aborted with this reason. |

- Column Explain:
  - AbortReason: group for Pareto of failure drivers.

---

- Table name: ManageRPQosDaily
- Priority: Normal
- What this table represents: Daily QoS for RP management APIs (Create/Delete/Update/Move/CheckNameAvailability and more).
- Freshness expectations: Daily; latency unknown.
- When to use:
  - Management plane QoS and volume by API/Region/CustomerType.
  - Rolling 7/28-day QoS anchored to latest day.
- When to avoid:
  - Data-plane QoS (use other QoS tables).
- Similar tables & how to choose:
  - No direct analog among data-plane QoS; this is management-plane focused.
- Common Filters:
  - ApiName inclusion/exclusion (exclude 'UNCATEGORY', internal-only).
  - CustomerType == 'SignalR' in examples.
- Table columns:

  | Column | Type | Description or meaning |
  |---|---|---|
  | Date | datetime | Day. |
  | ApiName | string | Management API name. |
  | SubscriptionId | string | Subscription GUID. |
  | CustomerType | string | Customer type. |
  | Region | string | Region. |
  | Result | string | Outcome (Success/Timeout/CustomerError/…). |
  | Count | long | Request count. |

- Column Explain:
  - QoS = (Success + Timeout + CustomerError) / Total; use sumif by Result set.

---

- Table name: Cached_TopSubscriptions_Snapshot
- Priority: High
- What this table represents: Cached snapshot of top subscriptions (service marked in a Service column).
- Freshness expectations: Snapshot; unknown cadence.
- When to use:
  - Seed sets of top subscriptions for correlating with recent activity (connections/messages/billing).
- When to avoid:
  - Comprehensive population analysis (not all subscriptions).
- Similar tables & how to choose:
  - Other Cached_* snapshot tables exist; pick based on scenario.
- Common Filters:
  - Service == 'WebPubSub' (as shown) or appropriate service.
- Table columns:

  | Column | Type | Description or meaning |
  |---|---|---|
  | SubscriptionId | string | Subscription id (join key). |
  | Revenue | real | Cached revenue indicator. |
  | MaxConnection | long | Cached max connection. |
  | MessageCount | long | Cached message count. |
  | StartDate | datetime | Window start for snapshot. |
  | EndDate | datetime | Window end for snapshot. |
  | TopRevenue | real | Rank metric. |
  | TopConnection | long | Rank metric. |
  | TopMessageCount | long | Rank metric. |
  | Rate | real | Relative rate/score. |
  | Service | string | Service (SignalR/WebPubSub). |

- Column Explain:
  - SubscriptionId: join to recent daily facts to build multi-metric views.

---

- Table name: ErrorsRedis_Hourly
- Priority: Normal
- What this table represents: Hourly Redis-related error counts by cluster/resource/pod.
- Freshness expectations: Hourly; latency unknown.
- When to use:
  - Track Redis error trends and affected resources.
- When to avoid:
  - Data-plane QoS percentages; use QoS tables instead.
- Similar tables & how to choose:
  - RuntimeExceptions_Hourly/RPExceptions_Hourly/RuntimeACSErrors_Daily for other error domains.
- Common Filters:
  - DateHour between startofday(now()) - N days.
  - Exclude ErrorType noise (e.g., not contains 'ks.').
- Table columns:

  | Column | Type | Description or meaning |
  |---|---|---|
  | DateHour | string | Hour slot (string formatted). |
  | Cluster | string | Cluster id (e.g., region shard letter). |
  | RedisId | string | Redis instance id. |
  | ResourceId | string | Resource id. |
  | PodName | string | Pod name. |
  | ErrorType | string | Error category. |
  | EventName | string | Event type. |
  | ErrorCount | long | Count in hour. |

- Column Explain:
  - Region derivation: Region = substring(Cluster,0,strlen(Cluster)-1) pattern used in queries.

---

- Table name: RuntimeExceptions_Hourly
- Priority: Normal
- What this table represents: Hourly runtime exceptions.
- Freshness expectations: Hourly; latency unknown.
- When to use:
  - Exception trending and top error types.
- When to avoid:
  - RP-level exceptions (use RPExceptions_Hourly).
- Common Filters:
  - Timestamp windows.
- Table columns:

  | Column | Type | Description or meaning |
  |---|---|---|
  | Timestamp | datetime | Hour. |
  | Cluster | string | Cluster. |
  | PodName | string | Pod. |
  | ResourceId | string | Resource. |
  | Logger | string | Logger source. |
  | ErrorType | string | Error category. |
  | ErrorMessage | string | Error message. |
  | Properties | string | Additional props. |
  | ErrorCount | long | Count in hour. |

---

- Table name: RPExceptions_Hourly
- Priority: Normal
- What this table represents: Hourly RP exception counts.
- Freshness expectations: Hourly; latency unknown.
- When to use:
  - RP exception trend by region/kind/reason.
- Common Filters:
  - Timestamp windows; Region dimension.
- Table columns:

  | Column | Type | Description or meaning |
  |---|---|---|
  | Timestamp | datetime | Hour. |
  | Region | string | Region. |
  | Cluster | string | Cluster. |
  | Kind | string | Component kind. |
  | Name | string | Exception name. |
  | Reason | string | Reason/category. |
  | Count | long | Count. |

---

- Table name: RuntimeACSErrors_Daily
- Priority: Normal
- What this table represents: Daily ACS-related errors by service component.
- Freshness expectations: Daily; latency unknown.
- When to use:
  - ACS error trending by ErrorType/ShortMessage.
- Common Filters:
  - Timestamp windows; service type and role instance.
- Table columns:

  | Column | Type | Description or meaning |
  |---|---|---|
  | Timestamp | datetime | Day. |
  | Region | string | Region. |
  | ServiceTypeName | string | Service type. |
  | RoleInstance | string | Instance. |
  | CorrelationRequestId | string | Correlation id. |
  | ErrorType | string | Error type. |
  | ShortMessage | string | Message. |
  | ErrorCount | long | Count. |

---

- Table name: RuntimeRequestsGroups_Daily
- Priority: Low
- What this table represents: Daily grouped runtime requests (categories/metrics).
- Freshness expectations: Daily; latency unknown.
- When to use:
  - Grouped request counts and resource counts by category/metric.
- Table columns:

  | Column | Type | Description or meaning |
  |---|---|---|
  | Date | datetime | Day. |
  | Category | string | Group/category. |
  | Metrics | string | Metric label. |
  | ResourceCount | long | Distinct resources. |
  | RequestCount | long | Request total. |

---

- Table name: RuntimeTransport_Daily
- Priority: Low
- What this table represents: Daily request counts by feature/transport/framework (data-plane).
- Freshness expectations: Daily; latency unknown.
- When to use:
  - Transport/framework adoption by feature.
- Common Filters:
  - Date windows; by ResourceId/SubscriptionId.
- Table columns:

  | Column | Type | Description or meaning |
  |---|---|---|
  | Date | datetime | Day. |
  | Feature | string | Feature area. |
  | Transport | string | Transport (e.g., WebSockets). |
  | Framework | string | SDK/framework (e.g., .NET). |
  | ResourceId | string | Resource. |
  | SubscriptionId | string | Subscription. |
  | RequestCount | long | Requests. |

---

- Table name: RuntimeTransport_EU_Daily
- Priority: Low
- What this table represents: EU-scoped variant of RuntimeTransport_Daily.
- Freshness expectations: Daily; latency unknown.
- When to use:
  - EU-only compliance or regional adoption cut.
- Table columns:

  | Column | Type | Description or meaning |
  |---|---|---|
  | Date | datetime | Day. |
  | Feature | string | Feature. |
  | Transport | string | Transport. |
  | Framework | string | Framework. |
  | ResourceId | string | Resource. |
  | SubscriptionId | string | Subscription. |
  | RequestCount | long | Requests. |

---

- Table name: AwpsRuntimeRequestsGroups_Daily
- Priority: Low
- What this table represents: AWPS-specific grouped runtime requests (daily).
- Freshness expectations: Daily; latency unknown.
- When to use:
  - AWPS product view of grouped requests.
- Table columns:

  | Column | Type | Description or meaning |
  |---|---|---|
  | Date | datetime | Day. |
  | Category | string | Category. |
  | Metrics | string | Metric. |
  | ResourceCount | long | Distinct resources. |
  | RequestCount | long | Requests. |

---

- Table name: WebTools_Raw (cluster("ddtelinsights").database("<DB>"))
- Priority: Low
- What this table represents: Client telemetry from Web Tools (used to derive developer states/usages related to SignalR).
- Freshness expectations: Appears near-real-time/daily; exact latency unknown.
- When to use:
  - Developer adoption signals (events and “state” for Service Dependencies tooling).
- When to avoid:
  - Service-side usage or billing (use product facts).
- Common Filters:
  - AdvancedServerTimestampUtc >= ago(30d).
  - EventName filters (e.g., 'vs/webtools/servicedependencies/state').
  - Measures/Properties contain 'signalr'.
- Columns used in queries (full schema unavailable cross-cluster):
  - AdvancedServerTimestampUtc (datetime)
  - EventName (string)
  - Properties (dynamic/string)
  - Measures (dynamic)
  - MacAddressHash (string)
  - ExeVersion (string)
- Column Explain:
  - EventName and Measures/Properties: derive State buckets (Suggested, Missing, Added, Ignored, Restored, AmbiguousConnection, Stale, Other).

---

- Table name: Requests (cluster("armprodgbl.eastus").database("<DB>"))
- Priority: Low
- What this table represents: ARM RP request logs.
- Freshness expectations: Near-real-time to hourly; unknown.
- When to use:
  - Detect Add/Delete EventGrid filters on SignalR resources (with HttpIncomingRequests).
- Common Filters:
  - TIMESTAMP > ago(30d), targetResourceProvider == 'MICROSOFT.SIGNALRSERVICE', httpMethod in ('PUT','DELETE'), targetResourceType == 'SIGNALR/EVENTGRIDFILTERS'.
- Columns used in queries (full schema not fetched cross-cluster):
  - TIMESTAMP (datetime), targetResourceProvider (string), httpMethod (string),
  - targetResourceType (string), subscriptionId (string),
  - targetUri (string), SourceNamespace (string)
- Column Explain:
  - Use targetUri to extract ResourceId; compute action (PUT=AddEventGrid, DELETE=DeleteEventGrid).

- Table name: HttpIncomingRequests (cluster("armprodgbl.eastus").database("<DB>"))
- Priority: Low
- What this table represents: ARM gateway incoming request logs (paired with Requests).
- Use and columns: same usage/filters as Requests; combined via Unionizer('Requests','HttpIncomingRequests').

Example EventGrid operations detection:
```kusto
Unionizer('Requests', 'HttpIncomingRequests')
| where TIMESTAMP > ago(30d)
  and targetResourceProvider == 'MICROSOFT.SIGNALRSERVICE'
  and httpMethod in ('PUT','DELETE')
  and targetResourceType == 'SIGNALR/EVENTGRIDFILTERS'
| extend ResourceId = substring(targetUri, 33, indexof(targetUri, '?') - 33),
         action = iif(httpMethod == 'PUT', 'AddEventGrid', 'DeleteEventGrid'),
         Date = startofday(TIMESTAMP),
         Location = trim_end('RPF', trim_start('csm', SourceNamespace))
| distinct Date, ResourceId, subscriptionId, action, Location
```

---

Additional guidance and patterns

- Normalizing Role/ResourceId:
```kusto
extend ResourceId = iif(Role has "replicas",
                        tolower(substring(Role, 0, indexof(Role, "/replicas/"))),
                        tolower(Role))
```

- Rolling QoS windows anchored to latest available date:
```kusto
let dateFilter = OperationQoS_Daily | top 1 by env_time desc | project env_time, fakeKey=1;
OperationQoS_Daily
| where env_time > ago(10d) and resourceId has "microsoft.signalrservice/signalr"
| extend fakeKey=1
| join kind=inner dateFilter on fakeKey
| where env_time > env_time1 - 7d
| summarize Qos = iif(sum(totalTimeSec)==0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec))
  by Date = env_time1, Type = "Rolling7"
```

- Weekly activity breadth (resources/subscriptions/customers):
```kusto
let Current = toscalar(MaxConnectionCount_Daily | top 1 by Date desc | project Date);
MaxConnectionCount_Daily
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
  and Date >= datetime_add('week', -10, startofweek(Current)) and Date < startofweek(Current)
  and Role contains "microsoft.signalrservice/signalr"
| extend Week = startofweek(Date)
| distinct Week, Role, SubscriptionId
| join kind=leftouter SubscriptionMappings on SubscriptionId
| summarize ResourceTotal = dcount(Role, 3),
            SubscriptionTotal = dcount(SubscriptionId, 3),
            CustomerTotal = dcount(CloudCustomerGuid, 3)
  by Week, CustomerType
```

- Web PubSub weekly multi-metric view:
```kusto
let label = "microsoft.signalrservice/webpubsub";
let base = (RPSettingLatest | extend ResourceId = tolower(ResourceId));
let withLabel = (tbl:(Date:datetime, Role:string, SubscriptionId:string, *) 
    {
      tbl
      | where Role has label
      | extend ResourceId = iif(Role has "replicas",
                                tolower(substring(Role, 0, indexof(Role, "/replicas/"))),
                                tolower(Role))
      | join kind=leftouter base on ResourceId
      | join kind=inner SubscriptionMappings on SubscriptionId
      | extend Kind = iif(Kind in ("", "SignalR"), "WebPubSub", Kind), CustomerType = CustomerType1
    });
withLabel(MaxConnectionCount_Daily)
| summarize SumValue = sum(MaxConnectionCount) by Date, CustomerType, Kind, BillingType, MetricsType="MaxConnectionCount"
| summarize Value = max(SumValue) by Week=startofweek(Date), CustomerType, Kind, BillingType, MetricsType
| union (
  withLabel(BoundTraffic_Daily | where MetricName == "OutboundTraffic")
  | summarize SumValue = sum(MessageCount) by Date, CustomerType, Kind, BillingType, MetricsType="OutboundTraffic"
  | summarize Value = sum(SumValue) by Week=startofweek(Date), CustomerType, Kind, BillingType, MetricsType
)
| union (
  withLabel(AvgConnectionCountEP_Daily)
  | summarize SumValue = sum(AvgConnectionCount) by Date, CustomerType, Kind, BillingType, MetricsType="AvgConnectionCount"
  | summarize Value = max(SumValue) by Week=startofweek(Date), CustomerType, Kind, BillingType, MetricsType
)
```

Notes and cautions
- Timezone and ingestion latency are not specified. When computing month-to-date or week-to-date, consider excluding the current unfinished day for accuracy.
- SLA thresholds (0.995 vs. 0.999) and revenue unit prices vary by KPI. Parameterize thresholds and use placeholders for prices (<UnitPrice_Standard>, <UnitPrice_Premium>).
- When joining by ResourceId, normalize to lowercase and remove “/replicas/…” suffix to avoid fragmentation.
- Cached_* snapshot tables are not comprehensive; absence implies “not in the cached set,” not necessarily “no usage.”


## Views (Reusable Layers)
None defined as first-class Kusto functions in the provided content. Several reusable query idioms and local lambdas (e.g., withLabel) are demonstrated below as building blocks.

## Query Building Blocks (Copy-paste snippets)
- Time window template (daily facts, effective end-time)
  
  kusto
  let DaysBack = 90d;
  let EffectiveEnd = startofday(now()); // guard against partial current day
  let StartDate = EffectiveEnd - DaysBack;
  <TableName>
  | where Date >= StartDate and Date < EffectiveEnd

- Time window template (rolling N-day window anchored to latest available date in a table)
  
  kusto
  let N = 28d;
  let AnchorDate = toscalar(<DailyTable> | top 1 by Date desc | project Date);
  <DailyTable>
  | where Date > AnchorDate - N and Date <= AnchorDate

- Completeness gate (multi-slice by Regions across two facts)
  
  kusto
  let MinSlices = 5;
  let LastCompleteDay =
      toscalar(
          union isfuzzy=true
              (MaxConnectionCount_Daily | summarize Slices=dcount(Region) by Date),
              (SumMessageCount_Daily | summarize Slices=dcount(Region) by Date)
          | summarize TotalSlices = sum(Slices) by Date
          | where TotalSlices >= MinSlices
          | top 1 by Date desc
          | project Date
      );
  <DailyTable>
  | where Date <= LastCompleteDay

- Join template (normalize Role → ResourceId; enrich with RPSettingLatest and SubscriptionMappings)
  
  kusto
  let baseSettings = RPSettingLatest | extend ResourceId = tolower(ResourceId);
  <DailyTable>
  | where Role has "<service-label>" // e.g., "microsoft.signalrservice/signalr"
  | extend ResourceId = iif(Role has "replicas",
                            tolower(substring(Role, 0, indexof(Role, "/replicas/"))),
                            tolower(Role))
  | join kind=leftouter baseSettings on ResourceId
  | join kind=inner SubscriptionMappings on SubscriptionId
  | project-away ResourceId1, SubscriptionId1, *1 // drop dup columns as needed

- De-dup pattern (latest snapshot per key)
  
  kusto
  <Table>
  | summarize arg_max(TimeCol, *) by <Key>

- Important filters (resource scope + internal exclusion)
  
  kusto
  | where (Role has "microsoft.signalrservice/signalr" or Role has "microsoft.signalrservice/webpubsub")
  | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())

- ARM ResourceId parsing from targetUri (Requests/HttpIncomingRequests)
  
  kusto
  | extend ResourceId = substring(targetUri, 33, indexof(targetUri, "?") - 33)

- Sharded union (same schema regional variants)
  
  kusto
  union isfuzzy=true RuntimeTransport_Daily, RuntimeTransport_EU_Daily
  | project-rename TimeCol = Date
  | summarize Requests = sum(RequestCount) by TimeCol, Feature, Transport, Framework

- Weekly aggregation semantics (Max vs Sum)
  
  kusto
  // Weekly Max of daily sums
  <DailyMaxMetricTable>
  | summarize SumValue = sum(<MaxMetric>) by Date, <Dims...>
  | summarize WeeklyValue = max(SumValue) by Week = startofweek(Date), <Dims...>
  //
  // Weekly Sum of daily sums
  <DailySumMetricTable>
  | summarize SumValue = sum(<SumMetric>) by Date, <Dims...>
  | summarize WeeklyValue = sum(SumValue) by Week = startofweek(Date), <Dims...>

## Example Queries (with explanations)
1) Billing revenue rollup by month, SKU, and customer segments

Description: Computes monthly revenue using BillingUsage_Daily for SignalR resources, excludes internal subscriptions, applies SKU-based unit prices (placeholders), and enriches with subscription segments. Adapt time via startofmonth window and expand to Web PubSub by changing filter and adding Kind/SKU splits.

kusto
let MonthsBack = 12;
BillingUsage_Daily
| where Date >= startofmonth(now(), -1 * MonthsBack) and ResourceId has "/signalr/"
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
| extend UnitPrice =
    case(SKU == "Free", 0.0,
         SKU == "Standard", <UnitPrice_Standard>,
         SKU == "Premium", <UnitPrice_Premium>, 0.0)
| extend Revenue = UnitPrice * Quantity
| join kind=inner SubscriptionMappings on SubscriptionId
| summarize Revenue = sum(Revenue) by Month = startofmonth(Date), SKU, CustomerType, BillingType
| order by Month asc, SKU asc

2) Weekly peak concurrent connections (SignalR) with settings and subscription enrichment

Description: For SignalR roles, normalizes Role → ResourceId, joins to RPSettingLatest and SubscriptionMappings, sums daily max connections per day, then computes the weekly max-of-sums. Adapt by changing label to webpubsub or by slicing by Region.

kusto
let label = "microsoft.signalrservice/signalr";
MaxConnectionCount_Daily
| where Date >= startofweek(now(), -26) and Date < startofweek(now()) and Role has label
| extend ResourceId = iif(Role has "replicas", tolower(substring(Role, 0, indexof(Role, "/replicas/"))), tolower(Role))
| join kind=leftouter (RPSettingLatest | extend ResourceId = tolower(ResourceId)) on ResourceId
| join kind=inner SubscriptionMappings on SubscriptionId
| summarize SumValue = sum(MaxConnectionCount) by Date, CustomerType=CustomerType1, ServiceMode, BillingType
| summarize Value = max(SumValue) by Week=startofweek(Date), CustomerType, ServiceMode, BillingType
| order by Week asc

3) Weekly message volume by customer type and billing type

Description: Aggregates SumMessageCount_Daily into weekly totals. Normalizes Role to ResourceId for consistent joins to dimensions, enriches with SubscriptionMappings, and sums messages by week. Adapt by including Region or splitting by service label for Web PubSub.

kusto
let EffectiveEnd = startofweek(now());
SumMessageCount_Daily
| where Date >= startofweek(EffectiveEnd, -26) and Date < EffectiveEnd
| where Role has "microsoft.signalrservice/signalr"
| extend ResourceId = iif(Role has "replicas", tolower(substring(Role, 0, indexof(Role, "/replicas/"))), tolower(Role))
| join kind=inner SubscriptionMappings on SubscriptionId
| summarize Value = sum(MessageCount) by Week = startofweek(Date), CustomerType, BillingType
| order by Week asc

4) Web PubSub weekly multi-metric view (connections, outbound traffic, avg connections)

Description: Demonstrates a reusable lambda to annotate tables with label, normalized ResourceId, RP settings, and mappings. Produces weekly max (for MaxConnectionCount/AvgConnectionCount) and weekly sum (for OutboundTraffic) views in one combined dataset. Adapt by adding other metrics or slicing by SKU/ServiceMode.

kusto
let label = "microsoft.signalrservice/webpubsub";
let base = (RPSettingLatest | extend ResourceId = tolower(ResourceId));
let withLabel = (tbl:(Date:datetime, Role:string, SubscriptionId:string, *) 
    {
      tbl
      | where Role has label
      | extend ResourceId = iif(Role has "replicas",
                                tolower(substring(Role, 0, indexof(Role, "/replicas/"))),
                                tolower(Role))
      | join kind=leftouter base on ResourceId
      | join kind=inner SubscriptionMappings on SubscriptionId
      | extend Kind = iif(Kind in ("", "SignalR"), "WebPubSub", Kind), CustomerType = CustomerType1
    });
withLabel(MaxConnectionCount_Daily)
| summarize SumValue = sum(MaxConnectionCount) by Date, CustomerType, Kind, BillingType, MetricsType="MaxConnectionCount"
| summarize Value = max(SumValue) by Week=startofweek(Date), CustomerType, Kind, BillingType, MetricsType
| union (
  withLabel(BoundTraffic_Daily | where MetricName == "OutboundTraffic")
  | summarize SumValue = sum(MessageCount) by Date, CustomerType, Kind, BillingType, MetricsType="OutboundTraffic"
  | summarize Value = sum(SumValue) by Week=startofweek(Date), CustomerType, Kind, BillingType, MetricsType
)
| union (
  withLabel(AvgConnectionCountEP_Daily)
  | summarize SumValue = sum(AvgConnectionCount) by Date, CustomerType, Kind, BillingType, MetricsType="AvgConnectionCount"
  | summarize Value = max(SumValue) by Week=startofweek(Date), CustomerType, Kind, BillingType, MetricsType
)
| order by Week asc, MetricsType asc

5) Operation QoS weekly rollup and SLA attainment by region

Description: Uses OperationQoS_Daily to compute QoS ratio with a zero-guard, then aggregates by week/region and calculates SLA attainment as the fraction of resources meeting a threshold. Adapt the <QoS_Threshold>, time window, or grouping to overall/global.

kusto
let QoSThreshold = 0.995;
OperationQoS_Daily
| where env_time > startofweek(now(), -8) and resourceId has "microsoft.signalrservice/signalr"
| summarize Qos = iif(sum(totalTimeSec)==0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec)),
          UpTime = sum(totalUpTimeSec), TotalTime = sum(totalTimeSec)
  by StartWeek = startofweek(env_time), Region = env_cloud_location, ResourceId = env_cloud_role
| summarize TotalOperation = sum(TotalTime),
          Qos = iif(sum(TotalTime)==0, 1.0, 1.0*sum(UpTime)/sum(TotalTime)),
          SlaAttainment = 1.0 * dcountif(ResourceId, Qos >= QoSThreshold, 4) / dcount(ResourceId, 4)
  by StartWeek, Region
| order by StartWeek asc, Region asc

6) Rolling 7-day Operation QoS anchored to latest available date

Description: Anchors to the latest env_time in OperationQoS_Daily, then forms a rolling 7-day window to compute QoS. Adapt the window length (e.g., 28d) or apply to ConnectivityQoS_Daily similarly.

kusto
let dateFilter = OperationQoS_Daily | top 1 by env_time desc | project env_time, fakeKey=1;
OperationQoS_Daily
| where env_time > ago(10d) and resourceId has "microsoft.signalrservice/signalr"
| extend fakeKey=1
| join kind=inner dateFilter on fakeKey
| where env_time > env_time1 - 7d
| summarize Qos = iif(sum(totalTimeSec)==0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec))
  by Date = env_time1, Type = "Rolling7"

7) Weekly activity breadth (distinct resources/subscriptions/customers)

Description: Anchors to the latest date in MaxConnectionCount_Daily and computes trailing 10 weeks of activity breadth, excluding internal subscriptions. Joins to SubscriptionMappings to count unique customers. Adapt the window size and change service label for Web PubSub.

kusto
let Current = toscalar(MaxConnectionCount_Daily | top 1 by Date desc | project Date);
MaxConnectionCount_Daily
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
  and Date >= datetime_add('week', -10, startofweek(Current)) and Date < startofweek(Current)
  and Role contains "microsoft.signalrservice/signalr"
| extend Week = startofweek(Date)
| distinct Week, Role, SubscriptionId
| join kind=leftouter SubscriptionMappings on SubscriptionId
| summarize ResourceTotal = dcount(Role, 3),
            SubscriptionTotal = dcount(SubscriptionId, 3),
            CustomerTotal = dcount(CloudCustomerGuid, 3)
  by Week, CustomerType
| order by Week asc

8) Detect ARM EventGrid filter add/delete operations for SignalR

Description: Unions ARM Requests and HttpIncomingRequests across cluster("armprodgbl.eastus"), filters to SignalR EventGridFilters operations, parses ResourceId from targetUri, and derives action (PUT/DELETE). Adapt by widening time, adding regions, or mapping to resource enrichments via joins.

kusto
cluster("armprodgbl.eastus").database("<DB>").Requests
| union cluster("armprodgbl.eastus").database("<DB>").HttpIncomingRequests
| where TIMESTAMP > ago(30d)
  and targetResourceProvider == 'MICROSOFT.SIGNALRSERVICE'
  and httpMethod in ('PUT','DELETE')
  and targetResourceType == 'SIGNALR/EVENTGRIDFILTERS'
| extend ResourceId = substring(targetUri, 33, indexof(targetUri, '?') - 33),
         action = iif(httpMethod == 'PUT', 'AddEventGrid', 'DeleteEventGrid'),
         Date = startofday(TIMESTAMP),
         Location = trim_end('RPF', trim_start('csm', SourceNamespace))
| distinct Date, ResourceId, subscriptionId, action, Location

9) Redis errors by region and resource (hourly)

Description: Tracks Redis-related errors, deriving Region from Cluster naming convention, and aggregates hourly counts to daily totals by Region and ResourceId. Adapt the ErrorType filter to focus on impactful categories; join to SubscriptionMappings for customer impact.

kusto
let Start = startofday(ago(14d));
ErrorsRedis_Hourly
| where todatetime(DateHour) >= Start
| extend TimeCol = todatetime(DateHour)
| extend Region = substring(Cluster, 0, strlen(Cluster)-1) // derive region from shard suffix
| where not(ErrorType contains "ks.") // example noise filter; refine as needed
| summarize ErrorCount = sum(ErrorCount) by Day = startofday(TimeCol), Region, ResourceId
| order by Day asc, ErrorCount desc

10) Runtime exceptions trend by error type (hourly)

Description: Summarizes RuntimeExceptions_Hourly by day and ErrorType for trend analysis. Use this to identify top regressions; adapt by slicing by ResourceId, Logger, or Region and correlating with deployment timelines.

kusto
let Start = startofday(ago(14d));
RuntimeExceptions_Hourly
| where Timestamp >= Start
| summarize ErrorCount = sum(ErrorCount) by Day = startofday(Timestamp), ErrorType
| order by Day asc, ErrorCount desc

## Reasoning Notes (only if uncertain)
- Timezone: Not specified. Adopt UTC as the default for startofweek/startofmonth/now to avoid locale variability.
- Ingestion freshness: Unknown for daily facts. Adopt an EffectiveEnd = startofday(now()) guard or LastCompleteDay gate to avoid partial current-day bias.
- Role normalization: Some facts log at Role granularity with “/replicas/…”. Adopt trimming to base ResourceId for consistent joins; alternative is to analyze per-replica where needed.
- SLA thresholds: Examples suggest 0.995 or 0.999. Adopt a parameter <QoS_Threshold> so analysts can set KPI-specific thresholds explicitly.
- Revenue pricing: Unit prices by SKU aren’t provided. Adopt placeholders (<UnitPrice_Standard>, <UnitPrice_Premium>) to avoid hardcoding; map per-SKU in a case() block.
- Customer dedupe: Multiple subscriptions can map to one customer. Adopt CloudCustomerGuid from SubscriptionMappings for deduplicated customer counts; alternative is P360_ID when internal alignment is required.
- Same-schema sharding: EU vs Global tables have the same schema. Adopt union isfuzzy=true then normalize TimeCol/keys before summarize; alternative is to keep separate and compare.
- Completeness slicing: Multi-slice gate uses Region distinct counts as a proxy. Adopt this as a conservative method; alternative gates include shard counts, service coverage, or lag-aware watermarks from ingestion metadata.
- Snapshot joins: RPSettingLatest is “latest” only. Adopt leftouter join for enrichment with the caveat that historical backfill may mismatch past states; alternative is to derive time-aware settings if a historical settings table becomes available.