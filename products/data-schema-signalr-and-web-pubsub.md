# SignalR and Web PubSub - Product and Data Overview Template

## 1. Product Overview

SignalR and Web PubSub is a real-time messaging and pub/sub services suite on Azure. This schema captures core facts, snapshots, and query playbooks used by PMAgent to analyze QoS/SLA, usage, customer/subscription/resource counts, retention, feature usage, and normalized revenue metrics for both SignalR and Web PubSub.

## 2. Data Platform Overview

- Data Storage: Azure Data Explorer (ADX)
- Product:
  SignalR and Web PubSub
- Product Nick Names:
  **[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations. (e.g., ASRS, SignalR Service, Web PubSub, AWPS)
- Kusto Cluster:
  signalrinsights.eastus2
- Kusto Database:
  SignalRBI
- Access Control:
  **[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed groups/users here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.

-----

# SignalR and Web PubSub — Kusto Query Playbook

## Overview
- Product: SignalR and Web PubSub
- Summary: Power Query M blocks referencing Azure Data Explorer (Kusto) via Kusto.Contents/AzureDataExplorer.Contents for SignalR and Web PubSub related datasets. Queries compute QoS/SLA, usage, customer/subscription/resource counts, retention, feature usage, and revenue-like metrics using pre-aggregated daily facts and cached snapshots.
- Primary cluster/database: signalrinsights.eastus2 / SignalRBI
  - Notes: Some datasets have EU shards (e.g., FeatureTrackV2_EU_Daily, RuntimeTransport_EU_Daily) that should be unioned with global equivalents.

## Conventions & Assumptions

- Time semantics
  - Timestamp columns observed:
    - env_time (OperationQoS_Daily, ConnectivityQoS_Daily)
    - Date (most daily facts)
    - AdvancedServerTimestampUtc (WebTools_Raw)
    - TimeStamp/TIMESTAMP (survey tables)
    - StartDate/EndDate (snapshot validity windows)
  - Canonical time column: TimeCol
    - Alias pattern:
      - For QoS tables: … | project-rename TimeCol = env_time
      - For daily facts: … | project-rename TimeCol = Date
      - For WebTools: … | project-rename TimeCol = AdvancedServerTimestampUtc
      - For snapshots with Month/Week “keys”: keep original (Month/Week) and compute a daily reference when needed via startofmonth()/startofweek()
  - Typical windows and bins:
    - last 30–60 days: where TimeCol > ago(30d)/ago(60d)
    - weekly grouping: startofweek(TimeCol)
    - monthly grouping: startofmonth(TimeCol)
    - rolling windows using “latest date” pattern (see templates below)
  - Timezone: Not specified; assume UTC. Caution: current day can be incomplete.

- Freshness & Completeness Gates
  - Ingestion is daily for most “_Daily” facts; current day may be incomplete.
  - Common “effective end date” gate:
    - Pick latest Date where sentinel slices (e.g., two regions or all expected regions) have data, then constrain downstream analysis to Date <= EndDate.
    - Example gate patterns seen:
      - two regions “australiaeast”, “westeurope”: dcount(Region) >= 2
      - global completeness: dcount(Region) >= 38
  - Recommendation if unknown: use previous full week or full month (e.g., Date < startofweek(now()) or Date < startofmonth(now())).

- Joins & Alignment
  - Frequent keys: ResourceId, SubscriptionId, Region, Role (acts as ResourceId in connection tables), CustomerType, CloudCustomerGuid
  - Common join kinds:
    - leftouter to enrich with settings/mappings (RPSettingLatest, SubscriptionMappings)
    - inner to restrict to valid cohorts/APIs or to enforce completeness lists
  - ResourceId normalization (important when joining):
    - tolower(ResourceId)
    - If Role contains “/replicas/…”, map to primary resource:
      - extend PrimaryResource = iif(Role has '/replicas/', substring(Role, 0, indexof(Role, '/replicas/')), Role)
    - Some queries derive SubscriptionId from ResourceId: extend SubscriptionId = tostring(split(ResourceId, '/')[2]) — verify your ResourceId format before use.
  - Post-join hygiene:
    - project-away duplicate columns (e.g., SKU and SKU1)
    - coalesce() or max() to select a single value after aggregation
    - project/extend to resolve naming clashes and normalize flags/types.

- Filters & Idioms
  - Service scoping:
    - SignalR: resourceId/Role has '/signalr/' or contains 'microsoft.signalrservice/signalr'
    - WebPubSub: resourceId/Role contains '/webpubsub/' or contains 'microsoft.signalrservice/webpubsub'
  - Exclude internal/test:
    - SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
  - ManageRP API filtering:
    - Exclude ApiName in ('UNCATEGORY') and often 'Internal-ACIS', 'INVALID', 'GetResource', 'OperationList', 'OperationResult', 'UpdateSubscription', and names containing 'acs'/'acis'
  - Case handling:
    - Use tolower() on join keys; prefer exact equality/has/contains per data usage:
      - has/contains frequently used on resourceId/Role provider paths (case-insensitive)

- Cross-cluster/DB & Sharding
  - EU shards: union tables with EU suffix counterparts (e.g., FeatureTrackV2_Daily union FeatureTrackV2_EU_Daily; RuntimeTransport_Daily union RuntimeTransport_EU_Daily)
  - Order matters: union → normalize (tolower, strip replicas, set Date = startofday()) → summarize
  - Fully qualify with cluster()/database() if your environment requires; here, everything is within signalrinsights.eastus2 / SignalRBI.

- Table classes
  - Fact (daily/event-level pre-aggregates): OperationQoS_Daily, ConnectivityQoS_Daily, MaxConnectionCount_Daily, SumMessageCount_Daily, AvgConnectionCountEP_Daily, BillingUsage_Daily, ManageRPQosDaily, ManageResourceTags, RuntimeTransport_Daily(_EU), FeatureTrack*_Daily, ConnectionMode_Daily, RuntimeResourceTags_Daily, BoundTraffic_Daily
  - Snapshot (latest or point-in-time state): RPSettingLatest; Cached_*_Snapshot families; Retention snapshots with StartDate/EndDate windows
  - Pre-aggregated KPIs: KPIv2019, KPI_AWPS, KPI_SocketIO, OKR* tables

## Entity & Counting Rules (Core Definitions)

- Entity model
  - Resource → Subscription → Customer
    - ResourceId: provider path (may include '/replicas/…'); normalize to primary for resource-level grouping
    - SubscriptionId: as provided in facts; sometimes derived from ResourceId
    - Customer: CloudCustomerGuid (and C360_ID/P360_ID for CRM alignment)
  - Standard grouping levels:
    - Resource-level (ResourceId or PrimaryResource)
    - Subscription-level (SubscriptionId)
    - Customer-level (CloudCustomerGuid or C360_ID)
    - Region, SKU, CustomerType, BillingType

- Business definitions (as used in queries)
  - QoS (Operation/Connectivity): sum(totalUpTimeSec) / sum(totalTimeSec) over the bin; if sum(totalTimeSec) == 0, set QoS = 1.0
  - SLA Attainment:
    - Operation QoS: threshold >= 0.999 (seen for SignalR; sometimes 0.995 weekly)
    - Connectivity QoS: threshold >= 0.995
    - Attainment by day/week: dcountif(ResourceId, Qos >= Threshold, 4) / dcount(ResourceId, 4)
  - ManageRP QoS:
    - SignalR: numerator includes Result in ('Success','Timeout','CustomerError')
    - WebPubSub: numerator sometimes only Result == 'Success'
    - Always confirm which definition applies to your report
  - Active resources (HasConnection): MaxConnectionCount > 0 (computed after joining MaxConnectionCount_Daily to usage)
  - LiveRatio classification by ActiveDays per period:
    - ActiveDays < 3 ⇒ Swift
    - 3 ≤ ActiveDays < 10 ⇒ Occasional
    - ≥ 10 ⇒ Dedicate
  - Premium replica usage: Replica presence detection with ResourceId has '/replicas/' and computing percentages in Premium SKU

## Canonical Tables

Note: All tables reside in cluster signalrinsights.eastus2, database SignalRBI unless stated. The lists below include all columns as provided.

### OperationQoS_Daily (Fact)
- Represents: Daily operation uptime/total time per environment role; use for service QoS/SLA.
- Use when:
  - Daily/weekly/monthly Operation QoS
  - SLA attainment across regions or overall
  - Rolling window QoS using latest available env_time
- Avoid when:
  - Connectivity-based QoS needed (use ConnectivityQoS_Daily)
  - Current day completeness is unknown; apply an effective end date gate
- Similar tables: ConnectivityQoS_Daily (connectivity QoS)
- Common Filters (important):
  - env_time > ago(…)
  - resourceId has 'microsoft.signalrservice/signalr' or contains 'webpubsub'
- Table columns:

  | Column                 | Type     | Description or meaning |
  |------------------------|----------|------------------------|
  | env_name               | string   | Environment name |
  | env_time               | datetime | Time of measurement (daily cadence) |
  | resourceId             | string   | Resource provider path (SignalR/WebPubSub) |
  | env_cloud_role         | string   | Resource role identifier |
  | env_cloud_roleInstance | string   | Instance identifier |
  | env_cloud_environment  | string   | Cloud environment |
  | env_cloud_location     | string   | Azure region |
  | env_cloud_deploymentUnit | string | Deployment unit |
  | totalUpTimeSec         | long     | Uptime seconds |
  | totalTimeSec           | long     | Total time seconds |

- Column Explain:
  - env_time: primary time column for QoS; alias to TimeCol
  - env_cloud_location: group by region
  - env_cloud_role/resourceId: resource identity; group and attainment dcount
  - totalUpTimeSec/totalTimeSec: compute QoS ratio

### ConnectivityQoS_Daily (Fact)
- Represents: Daily connectivity QoS (up vs. total).
- Use when:
  - Connectivity QoS and related SLA attainment
- Avoid when:
  - Operation QoS is needed
- Similar tables: OperationQoS_Daily
- Common Filters:
  - env_time thresholds; resourceId contains 'signalr' or 'webpubsub'
- Columns: same structure as OperationQoS_Daily (env_* + totals)
- Column Explain:
  - Same semantics as OperationQoS_Daily; threshold typically 0.995

### MaxConnectionCount_Daily (Fact)
- Represents: Daily maximum concurrent connections per role/resource.
- Use when:
  - Determine HasConnection (MaxConnectionCount > 0)
  - Weekly maxima by week
  - LiveRatio by ActiveDays per period
- Avoid when:
  - Message volume counts are required (use SumMessageCount_Daily)
- Similar tables: AvgConnectionCountEP_Daily (endpoint avg)
- Common Filters:
  - Role has '/signalr/' or contains 'webpubsub'
  - SubscriptionId !in SignalRTeamInternalSubscriptionIds()
- Columns:

  | Column            | Type     | Description |
  |-------------------|----------|-------------|
  | Date              | datetime | Observation date |
  | Role              | string   | Resource identifier (acts as ResourceId; may include '/replicas/') |
  | SubscriptionId    | string   | Subscription |
  | CustomerType      | string   | Customer type |
  | Region            | string   | Azure region |
  | MaxConnectionCount| long     | Maximum concurrent connections |

- Column Explain:
  - Role: normalize to primary resource by stripping '/replicas/'
  - MaxConnectionCount: active signal; used to compute HasConnection

### SumMessageCount_Daily (Fact)
- Represents: Daily total message count per role/subscription/customer type.
- Use when:
  - Summing message volumes, deriving usage intensity over weeks/months
- Common Filters: Role has '/signalr/' or '/webpubsub/'
- Columns:

  | Column         | Type     | Description |
  |----------------|----------|-------------|
  | Date           | datetime | Date |
  | Role           | string   | ResourceId-like role |
  | Region         | string   | Region |
  | SubscriptionId | string   | Subscription |
  | CustomerType   | string   | Customer type |
  | MessageCount   | long     | Total message count |

- Column Explain:
  - Used in weekly/monthly aggregations and top subscription analyses

### AvgConnectionCountEP_Daily (Fact)
- Represents: Daily average connection count per endpoint.
- Use when:
  - Endpoint-level connection intensity; weekly maxima per cohort
- Columns:

  | Column            | Type     | Description |
  |-------------------|----------|-------------|
  | Date              | datetime | Date |
  | Role              | string   | Resource role |
  | SubscriptionId    | string   | Subscription |
  | CustomerType      | string   | Customer type |
  | Region            | string   | Region |
  | Endpoint          | string   | Endpoint name |
  | AvgConnectionCount| long     | Avg connections |

- Column Explain:
  - Aggregated up to resource or cohort level; complements MaxConnectionCount_Daily

### RPSettingLatest (Snapshot)
- Represents: Latest resource provider settings (per resource).
- Use when:
  - Enriching resources with SKU, Kind, ServiceMode, flags (e.g., isAspire)
- Common Filters: ResourceId has '/Microsoft.SignalRService/SignalR/' or '/Microsoft.SignalRService/WebPubSub/'
- Columns:

  | Column                | Type     | Description |
  |-----------------------|----------|-------------|
  | ResourceId            | string   | Resource id |
  | Region                | string   | Region |
  | SKU                   | string   | Provisioned SKU |
  | Kind                  | string   | Service kind (SignalR/WebPubSub/SocketIO) |
  | State                 | string   | Resource state |
  | ServiceMode           | string   | Serverless/Default/… (sometimes nested in Extras for SocketIO) |
  | IsUpstreamSet         | bool     | Feature flag |
  | IsEventHandlerSet     | bool     | Feature flag |
  | EnableTlsClientCert   | bool     | Feature flag |
  | IsPrivateEndpointSet  | bool     | Feature flag |
  | EnablePublicNetworkAccess | bool | Flag |
  | DisableLocalAuth      | bool     | Flag |
  | DisableAadAuth        | bool     | Flag |
  | IsServerlessTimeoutSet| bool     | Flag |
  | AllowAnonymousConnect | bool     | Flag |
  | EnableRegionEndpoint  | bool     | Flag |
  | ResourceStopped       | bool     | State flag |
  | EnableLiveTrace       | bool     | Flag |
  | EnableResourceLog     | bool     | Flag |
  | LastUpdated           | datetime | Last update time |
  | Extras                | string   | JSON extras (e.g., $.socketIO.serviceMode, isAspire) |

- Column Explain:
  - SKU/Kind/ServiceMode: critical for segmentation (Premium, SocketIO, Serverless)
  - Extras: use extract_json for nested settings

### SubscriptionMappings (Dimension)
- Represents: Subscription to customer metadata mapping.
- Use when:
  - Enriching facts with CustomerType, CloudCustomerGuid, Offer/Billing/Segment info
- Columns:

  | Column            | Type   | Description |
  |-------------------|--------|-------------|
  | P360_ID           | string | CRM id |
  | CloudCustomerGuid | string | Customer GUID |
  | SubscriptionId    | string | Subscription id |
  | CustomerType      | string | Customer Type (External/Internal/…) |
  | CustomerName      | string | Display name |
  | SegmentName       | string | Segment |
  | OfferType         | string | Offer type |
  | OfferName         | string | Offer name |
  | BillingType       | string | Billing type |
  | WorkloadType      | string | Workload type |
  | S500              | string | Segment flag |

- Column Explain:
  - CustomerType/BillingType: used to segment KPIs and revenue-like metrics
  - CloudCustomerGuid: for customer-level counts

### BillingUsage_Daily (Fact)
- Represents: Daily billed usage quantities per resource/SKU.
- Use when:
  - Paid unit totals, normalized revenue (using placeholders/prices)
  - Cohorting by SKU/Region/CustomerType/BillingType
  - Completeness gate (count regions/day)
- Common Filters: ResourceId has '/signalr/' or '/webpubsub/'; exclude internal subs; SKU filters exclude 'MessageCount' for Premium/Standard only analyses
- Columns:

  | Column         | Type     | Description |
  |----------------|----------|-------------|
  | Date           | datetime | Usage date |
  | Region         | string   | Region |
  | SubscriptionId | string   | Subscription |
  | ResourceId     | string   | Resource provider path |
  | SKU            | string   | SKU (Free/Standard/Premium/MessageCount…) |
  | Quantity       | real     | Usage quantity |

- Column Explain:
  - Quantity: base for paid units
  - SKU: used for billing segmentation
  - Region: used for completeness gate EndDate derivation

### ManageRPQosDaily (Fact)
- Represents: Daily RP API QoS and counts.
- Use when:
  - QoS for management plane APIs by region/time
  - API-level breakdowns and weekly/monthly rollups
- Common Filters:
  - CustomerType in ('SignalR','WebPubSub','')
  - ApiName exclusions listed in Filters & Idioms
- Columns:

  | Column         | Type     | Description |
  |----------------|----------|-------------|
  | Date           | datetime | Date |
  | ApiName        | string   | API name |
  | SubscriptionId | string   | Subscription |
  | CustomerType   | string   | Product grouping |
  | Region         | string   | Region |
  | Result         | string   | API result (Success/Timeout/CustomerError/…) |
  | Count          | long     | Count per result |

- Column Explain:
  - Used to compute QoS = sumif(Count, Result in …)/sum(Count), mindful of numerator definition per product

### ManageResourceTags (Fact)
- Represents: Management operations related to resource tags.
- Use when:
  - Analyzing tag operations by RequestName/method
  - Joining to SubscriptionMappings for cohorting
- Columns:

  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Date          | datetime | Date |
  | SubscriptionId| string   | Subscription |
  | ResourceId    | string   | Resource |
  | RequestName   | string   | Operation name |
  | Tags          | string   | Operation tags (method) |
  | Count         | long     | Operation count |

- Column Explain:
  - RequestName/Tags: used for operation categorization

### RuntimeTransport_Daily and RuntimeTransport_EU_Daily (Fact, sharded)
- Represents: Runtime transport/feature usage counts.
- Use when:
  - Transport breakdown across frameworks
  - Union with EU shard then summarize
- Columns:

  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Date          | datetime | Date |
  | Feature       | string   | Feature |
  | Transport     | string   | Transport |
  | Framework     | string   | Framework |
  | ResourceId    | string   | Resource |
  | SubscriptionId| string   | Subscription |
  | RequestCount  | long     | Count |

- Column Explain:
  - Summarize RequestCount by Date/Category='Transport', Metrics=strcat(Framework, '-', Transport)

### FeatureTrackV2_Daily and FeatureTrackV2_EU_Daily (Fact, sharded)
- Represents: Feature tracking counts (v2 schema).
- Use when:
  - Feature usage cohorts; weekly aggregates; join with BillingUsage_Daily (SKU != 'MessageCount')
- Columns:

  | Column         | Type     | Description |
  |----------------|----------|-------------|
  | Date           | datetime | Date |
  | Feature        | string   | Feature name |
  | Category       | string   | Category |
  | ResourceId     | string   | Resource |
  | SubscriptionId | string   | Subscription |
  | Properties     | string   | Raw properties (often dropped) |
  | RequestCount   | long     | Count |

- Column Explain:
  - Use project-away Properties to reduce payload; derive cleaned Category as needed

### FeatureTrack_Daily (Fact)
- Columns:

  | Column         | Type     | Description |
  |----------------|----------|-------------|
  | Date           | datetime | Date |
  | Feature        | string   | Feature |
  | Category       | string   | Category |
  | ResourceId     | string   | Resource |
  | SubscriptionId | string   | Subscription |
  | RequestCount   | long     | Count |

- Use to compute subscription-level flags (e.g., NeededScale, MultiEndpoints)

### FeatureTrack_AutoScale_Daily (Fact)
- Columns:

  | Column         | Type     | Description |
  |----------------|----------|-------------|
  | Date           | datetime | Date |
  | Region         | string   | Region |
  | ResourceId     | string   | Resource |
  | SubscriptionId | string   | Subscription |
  | RequestCount   | long     | Autoscale feature events |

- Use when:
  - Counting resources with autoscale activity and computing % in Premium after join with BillingUsage_Daily (SKU == 'Premium')

### ConnectionMode_Daily (Fact)
- Represents: Daily connection mode counts (serverless vs proxy).
- Columns:

  | Column             | Type     | Description |
  |--------------------|----------|-------------|
  | Date               | datetime | Date |
  | ResourceId         | string   | Resource |
  | ServerlessConnection| long    | Count serverless |
  | ProxyConnection    | long     | Count proxy |
  | ServiceMode        | string   | Mode |

- Use to flag IsServerless/IsServerMode by subscription

### RuntimeResourceTags_Daily (Fact)
- Represents: Resource tagging signals for runtime behavior.
- Columns:

  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Date          | datetime | Date |
  | ResourceId    | string   | Resource |
  | SubscriptionId| string   | Subscription |
  | ServiceType   | string   | SignalR/WebPubSub |
  | IsAppService  | bool     | Flag |
  | IsStaticApps  | bool     | Flag |
  | IsSample      | bool     | Flag |
  | IsProxy       | bool     | Flag |
  | HasFailure    | bool     | Flag |
  | HasSuccess    | bool     | Flag |
  | Extra         | string   | Extra |

- Use to derive Samples/AppService/Proxy usage at subscription

### CustomerModel (Dimension)
- Represents: Customer/subscription CRM alignment.
- Columns:

  | Column                     | Type     |
  |----------------------------|----------|
  | C360_ID                    | string   |
  | CustomerName               | string   |
  | CloudCustomerGuid          | string   |
  | CloudCustomerName          | string   |
  | TPID                       | int      |
  | TPName                     | string   |
  | CustomerType               | string   |
  | SubscriptionId             | string   |
  | FriendlySubscriptionName   | string   |
  | WorkloadType               | string   |
  | BillingType                | string   |
  | OfferType                  | string   |
  | OfferName                  | string   |
  | CurrentSubscriptionStatus  | string   |
  | SegmentName                | string   |
  | P360_ID                    | string   |
  | P360_CustomerDisplayName   | string   |
  | SubscriptionCreatedDate    | datetime |
  | S500                       | string   |

- Used to surface CX links, customer display names, and segments

### Cached_ResourceFlow_Snapshot (Snapshot)
- Represents: Cached weekly/monthly resource counts by category/service type.
- Columns:

  | Column       | Type     |
  |--------------|----------|
  | Category     | string   |
  | Region       | string   |
  | SKU          | string   |
  | HasConnection| bool     |
  | LiveRatio    | string   |
  | ResourceCnt  | long     |
  | Date         | datetime |
  | ServiceType  | string   |
  | Partition    | string   |  (Week/Month)

- Use to quickly plot resource cohorts without recomputation

### Cached_SubsTotalWeekly_Snapshot (Snapshot)
- Columns:

  | Column        | Type     |
  |---------------|----------|
  | Week          | datetime |
  | ServiceType   | string   |
  | SubscriptionId| string   |
  | Region        | string   |
  | SKU           | string   |
  | HasConnection | bool     |
  | LiveRatio     | string   |

- Often joined to SubscriptionMappings then summarized

### Cached_SubsTotalMonthly_Snapshot (Snapshot)
- Columns:

  | Column        | Type     |
  |---------------|----------|
  | Month         | datetime |
  | ServiceType   | string   |
  | SubscriptionId| string   |
  | Region        | string   |
  | SKU           | string   |
  | HasConnection | bool     |
  | LiveRatio     | string   |

### Cached_CustomerFlow_Snapshot (Snapshot)
- Columns:

  | Column          | Type     |
  |-----------------|----------|
  | Category        | string   |
  | Region          | string   |
  | SKU             | string   |
  | HasConnection   | bool     |
  | LiveRatio       | string   |
  | CustomerType    | string   |
  | SegmentationType| string   |
  | CustomerCnt     | long     |
  | Date            | datetime |
  | ServiceType     | string   |
  | Partition       | string   |

### Cached_Asrs_TopCustomersWoW_v2_Snapshot (Snapshot)
- Columns:

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

### KPIv2019 / KPI_AWPS / KPI_SocketIO (Pre-aggregated)
- Columns:

  | Table         | Columns |
  |---------------|---------|
  | KPIv2019      | Date (datetime), SubscriptionCount (long), ResourceCount (long) |
  | KPI_AWPS      | Date (datetime), SubscriptionCount (long), ResourceCount (long) |
  | KPI_SocketIO  | Date (datetime), SubscriptionCount (long), ResourceCount (long) |

### OKR/OKRv2021, OKRv2021_AWPS, OKRv2021_SocketIO, OKR_AWPS_SocketIO
- Columns:

  | Table               | Columns |
  |---------------------|---------|
  | OKRv2021            | Date (datetime), Category (string), Value (real) |
  | OKRv2021_AWPS       | Date (datetime), Category (string), Value (real) |
  | OKRv2021_SocketIO   | Date (datetime), Category (string), Value (real) |
  | OKR_AWPS_SocketIO   | Date (datetime), CustomerType (string), Value (int) |

### ChurnCustomers_Monthly / ConvertCustomer_Weekly
- Columns:

  | Table                    | Columns |
  |--------------------------|---------|
  | ChurnCustomers_Monthly   | Month (datetime), ServiceType (string), Total (long), Churn (long), Standard (long), StandardChurn (long), RunDay (datetime) |
  | ConvertCustomer_Weekly   | Week (datetime), ServiceType (string), FreeToStandard (long), TotalCustomers (long), StandardCustomers (long), RunDay (datetime), FreeToPaid (long), StandardToPremium (long), FreeToPremium (long), PremiumCustomers (long) |

### Retention snapshots (AwpsRetention_* and *RetentionSnapshot)
- Columns: each has Id + StartDate + EndDate. Use for cohort retention.
  - AwpsRetention_SubscriptionSnapshot: SubscriptionId, StartDate, EndDate
  - AwpsRetention_CustomerSnapshot: C360_ID, StartDate, EndDate
  - AwpsRetention_ResourceSnapshot: ResourceId, StartDate, EndDate
  - SubscriptionRetentionSnapshot: SubscriptionId, StartDate, EndDate
  - CustomerRetentionSnapshot: C360_ID, StartDate, EndDate
  - ResourceRetentionSnapshot: ResourceId, StartDate, EndDate

### BoundTraffic_Daily (Fact)
- Columns:

  | Column        | Type     |
  |---------------|----------|
  | Date          | datetime |
  | Role          | string   |
  | Region        | string   |
  | SubscriptionId| string   |
  | Endpoint      | string   |
  | MetricName    | string   |
  | CustomerType  | string   |
  | MessageCount  | long     |

- Use OutboundTraffic for WebPubSub weekly cohorts

### Surveys & Tools
- DeleteSurvey / DeleteSurveyWebPubSub:

  | Column     | Type     |
  |------------|----------|
  | TIMESTAMP  | datetime |
  | Deployment | string   |
  | resourceId | string   |
  | reason     | string   |
  | feedback   | string   |
  | objectId   | string   |
  | sessionId  | string   |

- FeedbackSurvey:

  | Column    | Type     |
  |-----------|----------|
  | TimeStamp | datetime |
  | CESValue  | int      |
  | CVAValue  | int      |
  | Comments  | string   |

- FeedbackSurveyWebPubSub:

  | Column    | Type     |
  |-----------|----------|
  | TimeStamp | datetime |
  | Type      | string   |
  | CESValue  | int      |
  | CVAValue  | int      |
  | Comments  | string   |

- WebTools_Raw (used for developer telemetry):

  | Column                      | Type     |
  |-----------------------------|----------|
  | AdvancedServerTimestampUtc  | datetime |
  | EventName                   | string   |
  | Properties                  | dynamic? |
  | Measures                    | dynamic? |
  | ExeVersion                  | string   |
  | MacAddressHash              | string   |
  | ActiveProjectId             | string   |

- Column Explain:
  - WebTools_Raw: Used with filters on EventName/Properties; derive aggregates like DevCount/PublishProjectDevCount

## Views (Reusable Layers)
- Not applicable (no views provided). However, many queries reference reusable Kusto functions (not listed here) such as:
  - SignalRTeamInternalSubscriptionIds()
  - Unionizer('Requests', …)
  - ResourceFlow_Weekly/Monthly, SubscriptionFlow_Weekly/Monthly, CustomerFlow_Weekly/Monthly
  - DailyResource(...)
  - These functions encapsulate cross-source unions, cohort construction, and caching. Prefer them when available.

## Query Building Blocks (Copy-paste snippets)

- Time window template (daily facts)
  ```kusto
  let WindowDays = 60d;
  <Table>
  | where Date > ago(WindowDays)
  | summarize ... by Date = startofday(Date)
  ```

- Effective end date (multi-slice completeness gate)
  ```kusto
  let EndDate = toscalar(
    BillingUsage_Daily
    | where Date > ago(10d) and Region in ('australiaeast', 'westeurope')
    | summarize regions = dcount(Region) by Date
    | where regions >= 2
    | top 1 by Date desc
    | project Date
  );
  <Table>
  | where Date > ago(61d) and Date <= EndDate
  ```

- Latest-date rolling window (QoS)
  ```kusto
  let dateFilter = OperationQoS_Daily
  | top 1 by env_time desc
  | project env_time, fakeKey = 1;
  OperationQoS_Daily
  | where env_time > ago(10d) and resourceId has 'microsoft.signalrservice/signalr'
  | extend fakeKey = 1
  | join kind=inner dateFilter on fakeKey
  | where env_time > env_time1 - 7d
  | summarize Qos = iif(sum(totalTimeSec) == 0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec))
            by Date = env_time1, Type = 'Rolling7'
  ```

- Join template (resource enrichment)
  ```kusto
  // Normalize resource ID and strip replicas before joining
  <FactTable>
  | extend ResourceId = tolower(iif(Role has '/replicas/', substring(Role, 0, indexof(Role, '/replicas/')), Role))
  | join kind=leftouter (RPSettingLatest | extend ResourceId = tolower(ResourceId)) on ResourceId
  | join kind=inner SubscriptionMappings on SubscriptionId
  | project-away <duplicate columns as needed>
  ```

- De-dup latest per key (arg_max)
  ```kusto
  <Table>
  | summarize arg_max(TimeCol, *) by <Key1>, <Key2>
  ```

- Important default filters
  ```kusto
  // Service scope
  | where ResourceId has '/signalr/' // or contains '/webpubsub/'
  // Exclude internal team subscriptions
  | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
  // ManageRP API filters
  | where ApiName !in ('INVALID', 'GetResource', 'OperationList', 'OperationResult', 'UpdateSubscription', 'UNCATEGORY')
  | where ApiName !contains 'acs' and ApiName !contains 'acis'
  ```

- ID parsing/derivation
  ```kusto
  // Derive SubscriptionId from ResourceId (verify format in your data)
  | extend SubscriptionId = tostring(split(ResourceId, '/')[2])

  // Primary resource from Role that may have replicas
  | extend PrimaryResource = iif(Role has '/replicas/', substring(Role, 0, indexof(Role, '/replicas/')), Role)
  ```

- Sharded union (EU + Global)
  ```kusto
  let FT_all =
    (FeatureTrackV2_Daily | project Date, Feature, Category, ResourceId, SubscriptionId, RequestCount)
    | union (FeatureTrackV2_EU_Daily | project Date, Feature, Category, ResourceId, SubscriptionId, RequestCount)
    | extend Date = startofday(Date), ResourceId = tolower(ResourceId);
  FT_all
  | summarize RequestCount = sum(RequestCount) by Week = startofweek(Date), Feature
  ```

## Example Queries (with explanations)

1) Operation QoS and SLA Attainment by Region (SignalR)
```kusto
let raw = OperationQoS_Daily
| where env_time > ago(43d) and resourceId has '/signalr/'
| summarize Qos = iif(sum(totalTimeSec) == 0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec)),
          UpTime = sum(totalUpTimeSec),
          TotalTime = sum(totalTimeSec)
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
    by Date, Region = 'Overall'
)
```
- Description: Computes daily Operation QoS per region and overall for SignalR, plus SLA attainment at 0.999 threshold. Adapt by changing time window, threshold (0.995), or resourceId filter for WebPubSub.

2) Rolling 7/28-day QoS using latest observed day (SignalR)
```kusto
let dateFilter = OperationQoS_Daily
| top 1 by env_time desc
| project env_time, fakeKey = 1;
OperationQoS_Daily
| where env_time > ago(10d) and resourceId has 'microsoft.signalrservice/signalr'
| extend fakeKey = 1
| join kind = inner dateFilter on fakeKey
| where env_time > env_time1 - 7d
| summarize Qos = iif(sum(totalTimeSec) == 0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec))
  by Date = env_time1, Type = 'Rolling7'
| union (
OperationQoS_Daily
| where env_time > ago(30d) and resourceId contains 'microsoft.signalrservice/signalr'
| extend fakeKey = 1
| join kind = inner dateFilter on fakeKey
| where env_time > env_time1 - 28d
| summarize Qos = iif(sum(totalTimeSec) == 0, 1.0, 1.0*sum(totalUpTimeSec)/sum(totalTimeSec))
  by Date = env_time1, Type = 'Rolling28'
)
```
- Description: Anchors rolling windows on the latest available env_time to avoid partial trailing windows. Use the same structure for ConnectivityQoS_Daily.

3) Weekly Metrics Union: Max Connections, Messages, Avg Connections (SignalR)
```kusto
let label = 'microsoft.signalrservice/signalr';
MaxConnectionCount_Daily
| where Date >= startofweek(now(), -26) and Date < startofweek(now()) and Role has label
| extend ResourceId = iif(Role has 'replicas', tolower(substring(Role, 0, indexof(Role, '/replicas/'))), tolower(Role))
| join kind = leftouter (RPSettingLatest | extend ResourceId = tolower(ResourceId)) on ResourceId
| join kind = inner SubscriptionMappings on SubscriptionId
| extend ServiceMode = iif(isempty(ServiceMode), 'Default', ServiceMode)
| project Date, CustomerType = CustomerType1, MaxConnectionCount, ResourceId, ServiceMode, BillingType
| summarize SumValue = sum(MaxConnectionCount) by Date, CustomerType, ServiceMode, BillingType, MetricsType = 'MaxConnectionCount'
| summarize Value = max(SumValue) by Week = startofweek(Date), CustomerType, ServiceMode, BillingType, MetricsType
| union (
  SumMessageCount_Daily
  | where Date >= startofweek(now(), -26) and Date < startofweek(now()) and Role has label
  | extend ResourceId = iif(Role has 'replicas', tolower(substring(Role, 0, indexof(Role, '/replicas/'))), tolower(Role))
  | join kind = leftouter (RPSettingLatest | extend ResourceId = tolower(ResourceId)) on ResourceId
  | join kind = inner SubscriptionMappings on SubscriptionId
  | extend ServiceMode = iif(isempty(ServiceMode), 'Default', ServiceMode)
  | project Date, CustomerType = CustomerType1, MessageCount, ResourceId, ServiceMode, BillingType
  | summarize SumValue = sum(MessageCount) by Date, CustomerType, ServiceMode, BillingType, MetricsType = 'MessageCount'
  | summarize Value = sum(SumValue) by Week = startofweek(Date), CustomerType, ServiceMode, BillingType, MetricsType
)
| union (
  AvgConnectionCountEP_Daily
  | where Date >= startofweek(now(), -26) and Date < startofweek(now()) and Role has label
  | extend ResourceId = iif(Role has 'replicas', tolower(substring(Role, 0, indexof(Role, '/replicas/'))), tolower(Role))
  | join kind = leftouter (RPSettingLatest | extend ResourceId = tolower(ResourceId)) on ResourceId
  | join kind = inner SubscriptionMappings on SubscriptionId
  | extend ServiceMode = iif(isempty(ServiceMode), 'Default', ServiceMode)
  | project Date, CustomerType = CustomerType1, AvgConnectionCount, ResourceId, ServiceMode, BillingType
  | summarize SumValue = sum(AvgConnectionCount) by Date, CustomerType, ServiceMode, BillingType, MetricsType = 'AvgConnectionCount'
  | summarize Value = max(SumValue) by Week = startofweek(Date), CustomerType, ServiceMode, BillingType, MetricsType
)
```
- Description: Produces weekly max/sum metrics across connection and message counts, enriched by RP settings and subscription mapping. Adapt label for WebPubSub.

4) Manage RP QoS (SignalR) with API Filtering and Overall
```kusto
ManageRPQosDaily
| where Date > ago(43d) and CustomerType == 'SignalR' and ApiName !in ('UNCATEGORY')
| summarize QoS = 1.0*sumif(Count, Result in ('Success','Timeout','CustomerError'))/sum(Count),
            TotalRequest = sum(Count)
  by Date, Region
| union (
  ManageRPQosDaily
  | where Date > ago(60d) and CustomerType == 'SignalR' and ApiName !in ('UNCATEGORY')
  | summarize QoS = 1.0*sumif(Count, Result in ('Success','Timeout','CustomerError'))/sum(Count),
              TotalRequest = sum(Count)
    by Date, Region = 'Overall'
)
```
- Description: Computes daily QoS and request totals for management APIs with exclusions. For WebPubSub, adjust numerator if only 'Success' should count.

5) Effective EndDate gate and HasConnection cohorting (SignalR)
```kusto
let EndDate = toscalar(
  BillingUsage_Daily
  | where Date > ago(10d) and Region in ('australiaeast', 'westeurope')
  | summarize counter = dcount(Region) by Date
  | where counter >= 2
  | top 1 by Date desc
  | project Date
);
BillingUsage_Daily
| where Date > ago(61d) and Date <= EndDate and ResourceId has 'microsoft.signalrservice/signalr'
| extend SubscriptionId = tostring(split(ResourceId, '/')[2])
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
| summarize SKU = max(SKU), Region = max(Region) by Date, ResourceId
| join kind = leftouter MaxConnectionCount_Daily on Date, $left.ResourceId == $right.Role
| extend HasConnection = iif(isempty(Role), false, MaxConnectionCount > 0)
| summarize Total = dcount(ResourceId) by Date, SKU, Region, HasConnection
```
- Description: Establishes a safe EndDate and counts active resources by SKU/Region/HasConnection. Adapt regions/threshold to your completeness criteria.

6) LiveRatio classification (SignalR, weekly)
```kusto
MaxConnectionCount_Daily
| where Date >= startofweek(now(), -8) and SubscriptionId !in (SignalRTeamInternalSubscriptionIds()) and Role has '/signalr/'
| join kind = inner BillingUsage_Daily on $left.Role == $right.ResourceId, Date
| summarize Conn = max(MaxConnectionCount), SKU = max(SKU), Region = max(Region1), ActiveDays = dcount(Date) by Week = startofweek(Date), ResourceId
| project Week, ResourceId, Category = 'Total', Region, SKU, HasConnection = Conn > 0,
         LiveRatio = case(ActiveDays < 3, 'Swift', 'Occasional')
| summarize ResourceCnt = dcount(ResourceId, 3) by Week, Category, Region, SKU, HasConnection, LiveRatio
```
- Description: Classifies resources into Swift/Occasional based on weekly ActiveDays and counts them by cohort. Extend to 'Dedicate' with ActiveDays ≥ 10 if using monthly.

7) Weekly metrics for WebPubSub (connections, outbound traffic, avg connections)
```kusto
let label = 'microsoft.signalrservice/webpubsub';
MaxConnectionCount_Daily
| where Date >= startofweek(now(), -26) and Date < startofweek(now()) and Role has label
| extend ResourceId = iif(Role has 'replicas', tolower(substring(Role, 0, indexof(Role, '/replicas/'))), tolower(Role))
| join kind = leftouter (RPSettingLatest | extend ResourceId = tolower(ResourceId)) on ResourceId
| join kind = inner SubscriptionMappings on SubscriptionId
| extend Kind = iif(Kind in ('', 'SignalR'), 'WebPubSub', Kind), CustomerType = CustomerType1
| summarize SumValue = sum(MaxConnectionCount) by Date, CustomerType, Kind, BillingType, MetricsType = 'MaxConnectionCount'
| summarize Value = max(SumValue) by Week = startofweek(Date), CustomerType, Kind, BillingType, MetricsType
| union (
  BoundTraffic_Daily
  | where Date >= startofweek(now(), -26) and Date < startofweek(now()) and Role has label and MetricName == 'OutboundTraffic'
  | extend ResourceId = iif(Role has 'replicas', tolower(substring(Role, 0, indexof(Role, '/replicas/'))), tolower(Role))
  | join kind = leftouter (RPSettingLatest | extend ResourceId = tolower(ResourceId)) on ResourceId
  | join kind = inner SubscriptionMappings on SubscriptionId
  | extend Kind = iif(Kind in ('', 'SignalR'), 'WebPubSub', Kind), CustomerType = CustomerType1
  | summarize SumValue = sum(MessageCount) by Date, CustomerType, Kind, BillingType, MetricsType = 'OutboundTraffic'
  | summarize Value = sum(SumValue) by Week = startofweek(Date), CustomerType, Kind, BillingType, MetricsType
)
| union (
  AvgConnectionCountEP_Daily
  | where Date >= startofweek(now(), -26) and Date < startofweek(now()) and Role has label
  | extend ResourceId = iif(Role has 'replicas', tolower(substring(Role, 0, indexof(Role, '/replicas/'))), tolower(Role))
  | join kind = leftouter (RPSettingLatest | extend ResourceId = tolower(ResourceId)) on ResourceId
  | join kind = inner SubscriptionMappings on SubscriptionId
  | extend Kind = iif(Kind in ('', 'SignalR'), 'WebPubSub', Kind), CustomerType = CustomerType1
  | summarize SumValue = sum(AvgConnectionCount) by Date, CustomerType, Kind, BillingType, MetricsType = 'AvgConnectionCount'
  | summarize Value = max(SumValue) by Week = startofweek(Date), CustomerType, Kind, BillingType, MetricsType
)
```
- Description: Mirrors the SignalR union but for WebPubSub, adding outbound traffic.

8) Monthly retention cohorts (Subscription-level)
```kusto
let initTime = datetime_add('year', -1, startofmonth(now()));
range x from 0 to 12 step 1
| extend RangeMonth = datetime_add('month', -1*x, startofmonth(now())), fakeKey = 1
| join kind = inner (
  SubscriptionRetentionSnapshot
  | where StartDate >= initTime
  | extend StartMonth = startofmonth(StartDate), fakeKey = 1
) on fakeKey
| extend Periods = datetime_diff('month', RangeMonth, StartMonth)
| where StartMonth <= RangeMonth and EndDate >= RangeMonth
| summarize Retain = dcount(SubscriptionId) by StartMonth, Periods
| join kind = inner (
  SubscriptionRetentionSnapshot
  | where StartDate >= initTime
  | extend StartMonth = startofmonth(StartDate)
  | distinct StartMonth, SubscriptionId, EndDate
  | summarize Total = dcount(SubscriptionId) by StartMonth
) on StartMonth
| project Month = StartMonth, Periods, Total, Retain, Ratio = 1.0*Retain/Total, Category = 'Subscription'
```
- Description: Builds retention matrix at monthly granularity using StartDate/EndDate windows. Replace SubscriptionRetentionSnapshot with Customer/Resource variants for other tiers.

9) Premium replica share over time (SignalR or WebPubSub)
```kusto
BillingUsage_Daily
| where ResourceId has 'microsoft.signalrservice/signalr' and Date >= startofweek(now(), -12) and SKU == 'Premium'
| extend IsReplicas = ResourceId has '/replicas/'
| extend PrimaryResource = iif(IsReplicas, substring(ResourceId, 0, indexof(ResourceId, '/replicas/')), '')
| summarize ResourceCount = dcountif(ResourceId, IsReplicas) + dcountif(PrimaryResource, IsReplicas),
          PrimaryCount = dcountif(PrimaryResource, IsReplicas),
          PercentInPremium = 1.0 * (dcountif(ResourceId, IsReplicas) + dcountif(PrimaryResource, IsReplicas)) / dcount(ResourceId)
  by Week = startofweek(Date)
```
- Description: Estimates the prevalence of replica-based scaling in Premium. Swap the service filter for WebPubSub accordingly.

10) Top subscriptions daily panel (SignalR)
```kusto
Cached_TopSubscriptions_Snapshot
| where Service == 'SignalR'
| project SubscriptionId
| join kind = inner (
  MaxConnectionCount_Daily | where Date > startofday(now(), -29) and Role has '/signalr/'
  | summarize MaxConnectionCount = sum(MaxConnectionCount) by Date, SubscriptionId
) on SubscriptionId
| join kind = inner (
  SumMessageCount_Daily | where Date > startofday(now(), -29) and Role has '/signalr/'
  | summarize MessageCount = sum(MessageCount) by Date, SubscriptionId
) on SubscriptionId, Date
| join kind = inner (
  BillingUsage_Daily | where Date > startofday(now(), -29) and ResourceId has '/signalr/'
  | extend Revenue = case(SKU=='Standard', <UnitPriceStandard>, SKU=='Premium', <UnitPricePremium>, SKU=='Free', 0.0, <UnitPriceDefault>) * Quantity
  | summarize Revenue = sum(Revenue), PaidUnits = sumif(Quantity, SKU in ('Standard', 'Premium')), ResourceCount = dcount(ResourceId) by Date, SubscriptionId
) on SubscriptionId, Date
| extend Temp = pack('PaidUnits', PaidUnits, 'Revenue', Revenue, 'Messages', MessageCount, 'Connections', MaxConnectionCount, 'Resources', ResourceCount)
| mv-expand kind = array Temp
| project Date, SubscriptionId, Category = tostring(Temp[0]), Value = toreal(Temp[1])
```
- Description: Produces a per-subscription time series across multiple KPIs. Replace <UnitPrice…> with your pricing constants.

## Reasoning Notes (only if uncertain)
- Timezone: Source data timezone is not specified. We assume UTC (consistent with ADX), but be cautious with “today” and prefer effective end date or previous full week/month.
- SubscriptionId parsing from ResourceId: Some queries use split(ResourceId, '/')[2], which in canonical Azure IDs would be 'subscriptions' (index 2) rather than the GUID (index 3). This implies ResourceId here may be a custom/shortened path. Verify your data format before reusing the split logic.
- ManageRP QoS numerator differences:
  - SignalR sums ('Success','Timeout','CustomerError') as “good” outcomes; WebPubSub examples sometimes only count 'Success'. Choose the definition matching your product report and keep it consistent across time and cohorts.