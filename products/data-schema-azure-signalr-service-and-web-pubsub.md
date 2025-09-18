# Azure SignalR Service and Web PubSub - Product and Data Overview Template

## 1. Product Overview

Azure SignalR Service and Web PubSub provide real-time messaging capabilities for applications. This onboarding schema packages a comprehensive Kusto Query Playbook and data conventions to enable PMAgent to interpret and analyze product-specific telemetry. The scope covers both Azure SignalR Service and Web PubSub using the primary ADX database (SignalRBI) on the signalrinsights.eastus2 cluster, with references to auxiliary sources (ARMProd and DDTelInsights) used by some queries.

## 2. Data Platform Overview

- Data Storage: Azure Data Explorer (ADX)
- Product:
  Azure SignalR Service and Web PubSub
- Product Nick Names: 
  [TODO]Data_Engineer: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations.
- Kusto Cluster:
  signalrinsights.eastus2
- Kusto Database:
  SignalRBI
- Access Control:
  [TODO] Data Engineer: If this product’s data has high confidentiality concerns, please specify the allowed groups/users here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

# Kusto Query Playbook: Azure SignalR Service and Web PubSub

## Overview
- Product: Azure SignalR Service and Web PubSub
- Summary: Power BI report blocks containing KQL queries for Azure SignalR Service and Web PubSub using the SignalRBI database on signalrinsights.eastus2, plus references to ARMProd and DDTelInsights sources.
- Primary cluster/database:
  - Cluster: signalrinsights.eastus2
  - Database: SignalRBI
- Alternate sources referenced:
  - ARMProd (cluster: armprodgbl.eastus)
  - DDTelInsights (cluster: ddtelinsights)

## Conventions & Assumptions

- Time semantics
  - Timestamp columns observed:
    - env_time (OperationQoS_Daily, ConnectivityQoS_Daily)
    - Date (most *_Daily, *_Weekly, *_Monthly, cached snapshots, KPIs/OKRs)
    - AdvancedServerTimestampUtc (WebTools_Raw)
    - TIMESTAMP (DeleteSurvey, DeleteSurveyWebPubSub)
    - StartDate/EndDate (retention snapshots)
  - Canonical time column: TimeCol
    - Alias pattern:
      - project-rename TimeCol = env_time
      - project-rename TimeCol = Date
      - project-rename TimeCol = AdvancedServerTimestampUtc
  - Typical windows and bins:
    - Rolling windows: last 7/28 days anchored to latest available TimeCol (Rolling7/28 patterns)
    - Fixed windows: ago(30d), ago(60d), ago(61d), startofweek(now(), -N), startofmonth(now(), -N), explicit start dates (e.g., datetime(20210426) for WebPubSub GA)
    - Bin/resolution: day via startofday(), week via startofweek(), month via startofmonth()
  - Timezone: not specified; assume UTC for all timestamps.

- Freshness & Completeness Gates
  - Current day is often incomplete; many queries anchor to the last complete day or use an EndDate gate.
  - Multi-slice completeness gates are used:
    - Gate by sufficient regional coverage, e.g.:
      - “latest Date where ≥2 of ['australiaeast','westeurope'] present”
      - “latest Date where ≥NRegions (e.g., 38) reported”
  - Effective end-time pattern:
    - Compute EndDate with toscalar(...) using a dcount over a sentinel slice (Region), then restrict facts to Date <= EndDate.
  - Recommendation when coverage unknown: use previous full week or previous full month ranges.

- Joins & Alignment
  - Frequent keys
    - ResourceId (may appear as Role in connection tables)
    - SubscriptionId
    - Region
    - SKU
    - ServiceType/Kind (SignalR vs WebPubSub vs SocketIO)
  - Key normalization
    - Lowercasing for string joins: extend ResourceId = tolower(ResourceId) (and Role), normalize both sides.
    - Remove replica suffix: iif(ResourceId has '/replicas/', substring(ResourceId, 0, indexof(ResourceId, '/replicas/')), ResourceId)
    - Parse SubscriptionId from ResourceId: tostring(split(ResourceId, '/')[2]) as used in existing queries.
  - Typical join kinds
    - leftouter to enrich fact tables with dimension/snapshot (e.g., RPSettingLatest, SubscriptionMappings)
    - inner to restrict to valid cohorts (e.g., only subscriptions in SubscriptionMappings, only valid ApiName list)
  - Post-join hygiene
    - Resolve duplicate columns explicitly: project-away duplicate SubscriptionId1/2/3, Region1, SKU1, Date1, etc.
    - Coalesce values after joins, or re-project canonical names:
      - project ResourceId = coalesce(ResourceId, Role), Region = coalesce(Region, Region1)
    - After unions, normalize keys/time, then summarize.

- Filters & Idioms
  - Resource filters:
    - SignalR: resourceId/Role has 'microsoft.signalrservice/signalr' or contains '/signalr/'
    - WebPubSub: resourceId/Role contains 'webpubsub' or has 'microsoft.signalrservice/webpubsub'
  - Operational filters:
    - ManageRP queries exclude ApiName in ('Internal-ACIS', 'UNCATEGORY', 'INVALID', 'GetResource', 'OperationList', 'OperationResult', 'UpdateSubscription'); also ApiName !contains 'acs'/'acis'
  - Cohorts:
    - Exclude team/internal subscriptions: SubscriptionId !in (SignalRTeamInternalSubscriptionIds()) [some queries show without parentheses; use the function form if available]
    - Allowlist cohort build: derive distinct ApiName/Resource list first, then join kind=inner to restrict.
  - Text predicates:
    - has is used for word-bound (faster) substring matches on ResourceId paths
    - contains for simple substring matches
    - Case handling: normalize with tolower() before equality joins.

- Cross-cluster/DB & Sharding
  - Cross-source references:
    - ARM requests: Requests, HttpIncomingRequests from armprodgbl.eastus
    - Developer telemetry: WebTools_Raw from ddtelinsights
  - Use fully qualified names when needed:
    - cluster('armprodgbl.eastus').database('<ARM_DB>').Requests
    - cluster('ddtelinsights').database('<DDTel_DB>').WebTools_Raw
  - Sharded tables (regional or EU variants) with same schema:
    - union FeatureTrackV2_Daily with FeatureTrackV2_EU_Daily
    - union RuntimeTransport_Daily with RuntimeTransport_EU_Daily
  - Order of operations: union → normalize (lowercase, strip replicas, canonical time) → summarize.

- Table classes
  - Fact (daily or events): OperationQoS_Daily, ConnectivityQoS_Daily, BillingUsage_Daily, MaxConnectionCount_Daily, SumMessageCount_Daily, AvgConnectionCountEP_Daily, ManageRPQosDaily, ConnectionMode_Daily, FeatureTrack* tables, BoundTraffic_Daily, RuntimeResourceTags_Daily, RuntimeTransport*_Daily, WebTools_Raw, ARM Requests/HttpIncomingRequests.
  - Snapshot (latest or range snapshots): RPSettingLatest (latest state), SubscriptionMappings (dimension mapping), Retention snapshots (with StartDate/EndDate), Cached_*_Snapshot pre-aggregates.
  - Pre-aggregated/KPI: KPI*, OKR*, Cached_* snapshots.
  - Usage rules:
    - Prefer fact tables for raw counting and flexible cuts.
    - Prefer snapshots/pre-aggregates for dashboards and faster pivots; validate freshness and partition (Week/Month) before mixing with facts.
    - Do not mix snapshot and daily facts without aligning time windows and keys.

## Entity & Counting Rules (Core Definitions)
- Entity model
  - Resource → Subscription → Customer
    - ResourceId: ARM resource path (may include '/replicas' for Premium)
    - SubscriptionId: subscription scope (also parsed from ResourceId)
    - Customer: CloudCustomerGuid or P360_ID (via SubscriptionMappings/CustomerModel)
  - Other grouping tiers:
    - Region, SKU, ServiceType/Kind (SignalR/WebPubSub/SocketIO), BillingType, OfferType/OfferName, CustomerType
- Counting rules
  - Active resource: often defined by HasConnection = max(MaxConnectionCount) > 0 across a period; activity classification via ActiveDays thresholds ('Swift' <3 days, 'Occasional' <10 days, else 'Dedicate')
  - QoS metrics:
    - Operation/Connectivity QoS = sum(totalUpTimeSec) / sum(totalTimeSec) with guard for zero denom
    - SlaAttainment = dcountif(ResourceId, Qos >= Threshold, <precision>)/dcount(ResourceId, <precision>); thresholds seen: 0.999 (Operation), 0.995 (Connectivity)
  - Manage/RP QoS: sum of “good” results / total; for SignalR: good = ('Success','Timeout','CustomerError'); for WebPubSub examples: good = 'Success'
  - Distinct counts use probabilistic dcount with precision parameters (3 or 4): dcount(<key>, 3)

## Canonical Tables
Below are the canonical tables used. For cross-source tables, the source cluster is prefixed. “Common Filters” are important defaults to apply.

### OperationQoS_Daily (signalrinsights.eastus2/SignalRBI)
- Represents: Daily fact of operation uptime/time by environment for SignalR/WebPubSub.
- Class: Fact (daily)
- Freshness: Ingested daily; current day may be incomplete.
- When to use:
  - Compute daily/weekly/monthly QoS and SLA attainment
  - Regional QoS breakdowns
  - Rolling window QoS anchored to latest day
- When to avoid:
  - If you need connectivity QoS, use ConnectivityQoS_Daily
  - Real-time needs; this is daily aggregated
- Similar tables: ConnectivityQoS_Daily (use for connectivity)
- Common Filters:
  - env_time within window (ago(), startofweek/startofmonth)
  - resourceId contains 'microsoft.signalrservice/signalr' or 'webpubsub'
- Table columns:

  | Column               | Type     | Description or meaning |
  |----------------------|----------|------------------------|
  | env_name             | string   | Environment name |
  | env_time             | datetime | Event/day time (canonical TimeCol) |
  | resourceId           | string   | Resource identifier or filter scope |
  | env_cloud_role       | string   | Role identifier (used as ResourceId in queries) |
  | env_cloud_roleInstance | string | Instance |
  | env_cloud_environment| string   | Cloud environment |
  | env_cloud_location   | string   | Region |
  | env_cloud_deploymentUnit | string | DU |
  | totalUpTimeSec       | long     | Up time in seconds |
  | totalTimeSec         | long     | Total time in seconds |

- Column Explain:
  - env_time: primary time for QoS; alias to Date/TimeCol
  - env_cloud_location: Region group by
  - env_cloud_role: often treated as ResourceId in QoS grouping
  - totalUpTimeSec/totalTimeSec: used to compute QoS ratios

### ConnectivityQoS_Daily (signalrinsights.eastus2/SignalRBI)
- Represents: Daily fact of connectivity uptime/time.
- Class: Fact (daily)
- Use for connectivity QoS and SLA thresholds (e.g., 0.995).
- Common Filters: Same as OperationQoS_Daily.
- Columns: identical to OperationQoS_Daily.

### MaxConnectionCount_Daily (signalrinsights.eastus2/SignalRBI)
- Represents: Daily max concurrent connections per resource/role.
- Class: Fact (daily)
- When to use:
  - Activity detection (HasConnection)
  - Peak connections trend by week/month
  - Join to usage/SKU via BillingUsage_Daily
- When to avoid:
  - Not for message counts (use SumMessageCount_Daily)
- Similar tables: AvgConnectionCountEP_Daily (average by endpoint)
- Common Filters:
  - Date within window
  - Role has '/signalr/' or contains 'webpubsub'
  - SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
- Columns:

  | Column             | Type     | Description or meaning |
  |--------------------|----------|------------------------|
  | Date               | datetime | Day key |
  | Role               | string   | Resource identifier path (acts like ResourceId) |
  | SubscriptionId     | string   | Subscription |
  | CustomerType       | string   | Customer classification |
  | Region             | string   | Region |
  | MaxConnectionCount | long     | Daily max connections |

- Column Explain:
  - Role: use as ResourceId; normalize tolower and strip '/replicas/'
  - MaxConnectionCount: primary activity signal
  - SubscriptionId/Region: for joining and slicing

### SubscriptionMappings (signalrinsights.eastus2/SignalRBI)
- Represents: Subscription → customer metadata mapping.
- Class: Dimension snapshot
- When to use:
  - Enrich facts with CustomerType, BillingType, Offer, CloudCustomerGuid
  - Group counts by customer segments
- Common Filters:
  - Joined via SubscriptionId
- Columns:

  | Column           | Type   | Description |
  |------------------|--------|-------------|
  | P360_ID          | string | P360 Id |
  | CloudCustomerGuid| string | Customer GUID |
  | SubscriptionId   | string | Subscription key |
  | CustomerType     | string | Customer type |
  | CustomerName     | string | Name |
  | SegmentName      | string | Segment |
  | OfferType        | string | Offer type |
  | OfferName        | string | Offer name |
  | BillingType      | string | Billing type |
  | WorkloadType     | string | Workload type |
  | S500             | string | S500 tag |

- Column Explain:
  - SubscriptionId: join key
  - CustomerType/BillingType/SegmentName: common slicing fields
  - CloudCustomerGuid/P360_ID: customer-level dedup/grouping

### BillingUsage_Daily (signalrinsights.eastus2/SignalRBI)
- Represents: Daily usage quantities and SKU for resources.
- Class: Fact (daily)
- When to use:
  - Paid/free units by SKU
  - Normalize revenue (use price placeholders)
  - Combine with connection/activity to classify active resources
- Common Filters:
  - Date window; ResourceId has '/signalr/' or '/webpubsub/'
  - SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
  - SKU in ('Free', 'Standard', 'Premium') or exclude message SKUs when needed
- Columns:

  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Date          | datetime | Day key |
  | Region        | string   | Region |
  | SubscriptionId| string   | Subscription |
  | ResourceId    | string   | ARM resource |
  | SKU           | string   | SKU name |
  | Quantity      | real     | Usage quantity |

- Column Explain:
  - SKU/Quantity: compute units and revenue
  - ResourceId/SubscriptionId: join to other facts/dimensions

### RPSettingLatest (signalrinsights.eastus2/SignalRBI)
- Represents: Latest resource properties/settings (state, kind, service mode, flags).
- Class: Snapshot (latest)
- When to use:
  - Enrich resources with Kind (SignalR/WebPubSub/SocketIO), ServiceMode, security toggles
  - Determine Socket.IO service mode (via Extras JSON)
- Common Filters:
  - Join by ResourceId (normalize tolower)
- Columns:

  | Column                 | Type     | Description |
  |------------------------|----------|-------------|
  | ResourceId             | string   | Resource key |
  | Region                 | string   | Region |
  | SKU                    | string   | SKU |
  | Kind                   | string   | Kind (SignalR/WebPubSub/SocketIO) |
  | State                  | string   | Resource state |
  | ServiceMode            | string   | Service mode |
  | IsUpstreamSet          | bool     | Upstream configured |
  | IsEventHandlerSet      | bool     | Event handler configured |
  | EnableTlsClientCert    | bool     | TLS client cert |
  | IsPrivateEndpointSet   | bool     | Private endpoint |
  | EnablePublicNetworkAccess | bool  | PNA enabled |
  | DisableLocalAuth       | bool     | Local auth disabled |
  | DisableAadAuth         | bool     | AAD auth disabled |
  | IsServerlessTimeoutSet | bool     | Serverless timeout |
  | AllowAnonymousConnect  | bool     | Anonymous connect |
  | EnableRegionEndpoint   | bool     | Region endpoint |
  | ResourceStopped        | bool     | Stopped flag |
  | EnableLiveTrace        | bool     | Live trace flag |
  | EnableResourceLog      | bool     | Resource log flag |
  | LastUpdated            | datetime | Update time |
  | Extras                 | string   | JSON extras (e.g., socketIO.serviceMode) |

- Column Explain:
  - Kind/ServiceMode: choose cohorts (WebPubSub, SocketIO; Serverless/Default)
  - Extras: parse JSON for advanced flags (e.g., socketIO.serviceMode)

### SumMessageCount_Daily (signalrinsights.eastus2/SignalRBI)
- Represents: Daily message count per subscription/resource.
- Class: Fact (daily)
- Use to measure volume; pair with connections for engagement.
- Columns:

  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Date          | datetime | Day key |
  | Role          | string   | Resource path |
  | Region        | string   | Region |
  | SubscriptionId| string   | Subscription |
  | CustomerType  | string   | Customer type |
  | MessageCount  | long     | Message count |

- Important: Role normalization as in MaxConnectionCount_Daily.

### AvgConnectionCountEP_Daily (signalrinsights.eastus2/SignalRBI)
- Represents: Daily average connections per endpoint.
- Class: Fact (daily)
- Columns:

  | Column             | Type     | Description |
  |--------------------|----------|-------------|
  | Date               | datetime | Day key |
  | Role               | string   | Resource path |
  | SubscriptionId     | string   | Subscription |
  | CustomerType       | string   | Customer type |
  | Region             | string   | Region |
  | Endpoint           | string   | Endpoint ID |
  | AvgConnectionCount | long     | Avg connections |

### ManageRPQosDaily (signalrinsights.eastus2/SignalRBI)
- Represents: Daily request/response outcomes for ARM RP operations.
- Class: Fact (daily)
- When to use:
  - RP QoS (success/timeouts/customer errors over total)
  - Breakdowns by ApiName, Region
- Common Filters:
  - ApiName not in ('Internal-ACIS', 'UNCATEGORY', 'INVALID', 'GetResource', 'OperationList', 'OperationResult', 'UpdateSubscription'); !contains 'acs'/'acis' for SignalR
  - CustomerType == 'SignalR' or 'WebPubSub' (context dependent)
- Columns:

  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Date          | datetime | Day key |
  | ApiName       | string   | Operation name |
  | SubscriptionId| string   | Subscription |
  | CustomerType  | string   | Product ('SignalR' or 'WebPubSub') |
  | Region        | string   | Region |
  | Result        | string   | Outcome category |
  | Count         | long     | Event count |

- Column Explain:
  - Result: compute QoS via sumif over “good” outcomes
  - ApiName: filter or cohort build

### ConnectionMode_Daily (signalrinsights.eastus2/SignalRBI)
- Represents: Daily connection mode counts.
- Class: Fact (daily)
- Columns:

  | Column             | Type     | Description |
  |--------------------|----------|-------------|
  | Date               | datetime | Day key |
  | ResourceId         | string   | Resource |
  | ServerlessConnection | long   | Serverless connections |
  | ProxyConnection    | long     | Server mode/proxy connections |
  | ServiceMode        | string   | Mode |

### RuntimeResourceTags_Daily (signalrinsights.eastus2/SignalRBI)
- Represents: Daily resource-level tags/flags derived at runtime.
- Class: Fact (daily)
- Columns:

  | Column         | Type     | Description |
  |----------------|----------|-------------|
  | Date           | datetime | Day key |
  | ResourceId     | string   | Resource |
  | SubscriptionId | string   | Subscription |
  | ServiceType    | string   | SignalR or WebPubSub |
  | IsAppService   | bool     | App Service tag |
  | IsStaticApps   | bool     | Static Apps tag |
  | IsSample       | bool     | Sample flag |
  | IsProxy        | bool     | Proxy usage flag |
  | HasFailure     | bool     | Indicates failure observed |
  | HasSuccess     | bool     | Indicates success observed |
  | Extra          | string   | Additional info |

### FeatureTrack_Daily (signalrinsights.eastus2/SignalRBI)
- Represents: Daily feature event counts (SignalR/WebPubSub).
- Class: Fact (daily)
- Columns:

  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Date          | datetime | Day key |
  | Feature       | string   | Feature name |
  | ResourceId    | string   | Resource |
  | SubscriptionId| string   | Subscription |
  | RequestCount  | long     | Request count |

### FeatureTrackV2_Daily, FeatureTrackV2_EU_Daily (signalrinsights.eastus2/SignalRBI)
- Represents: Daily feature telemetry with Category and Properties; EU shard replicated in _EU_ table.
- Class: Fact (daily), Sharded
- Columns:

  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Date          | datetime | Day key |
  | Feature       | string   | Feature |
  | Category      | string   | Category (may contain 'Ping...' variants) |
  | ResourceId    | string   | Resource |
  | SubscriptionId| string   | Subscription |
  | Properties    | string   | JSON properties |
  | RequestCount  | long     | Requests |

### FeatureTrack_AutoScale_Daily (signalrinsights.eastus2/SignalRBI)
- Represents: AutoScale-related feature events count.
- Class: Fact (daily)
- Columns:

  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Date          | datetime | Day |
  | Region        | string   | Region |
  | ResourceId    | string   | Resource |
  | SubscriptionId| string   | Subscription |
  | RequestCount  | long     | Requests |

### CustomerModel (signalrinsights.eastus2/SignalRBI)
- Represents: Customer enrichment model for Top Subscriptions.
- Columns: Not provided in input.

### Cached_TopSubscriptions_Snapshot (signalrinsights.eastus2/SignalRBI)
- Represents: Pre-aggregated metrics for top subscriptions within a [StartDate, EndDate] window.
- Class: Pre-aggregated snapshot
- Columns:

  | Column         | Type     | Description |
  |----------------|----------|-------------|
  | SubscriptionId | string   | Subscription |
  | Revenue        | real     | Aggregated revenue (normalized) |
  | MaxConnection  | long     | Max connections |
  | MessageCount   | long     | Messages |
  | StartDate      | datetime | Start of window |
  | EndDate        | datetime | End of window |
  | TopRevenue     | real     | Rankable revenue |
  | TopConnection  | long     | Rankable connections |
  | TopMessageCount| long     | Rankable messages |
  | Rate           | real     | Derived rate/ratio |
  | Service        | string   | Service (SignalR/WebPubSub) |

### Cached_SubsTotalWeekly_Snapshot (signalrinsights.eastus2/SignalRBI)
- Represents: Weekly pre-aggregated subscription totals and attributes.
- Class: Pre-aggregated snapshot (Week)
- Columns:

  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Week          | datetime | Week key |
  | ServiceType   | string   | Product |
  | SubscriptionId| string   | Subscription |
  | Region        | string   | Region |
  | SKU           | string   | SKU |
  | HasConnection | bool     | Has connections during period |
  | LiveRatio     | string   | Activity classification |

### Cached_SubsTotalMonthly_Snapshot (signalrinsights.eastus2/SignalRBI)
- Represents: Monthly pre-aggregated subscription totals and attributes.
- Class: Pre-aggregated snapshot (Month)
- Columns:

  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Month         | datetime | Month key |
  | ServiceType   | string   | Product |
  | SubscriptionId| string   | Subscription |
  | Region        | string   | Region |
  | SKU           | string   | SKU |
  | HasConnection | bool     | Has connections |
  | LiveRatio     | string   | Activity classification |

### Cached_CustomerFlow_Snapshot (signalrinsights.eastus2/SignalRBI)
- Represents: Pre-aggregated customer flow by category and partition (Week/Month).
- Class: Pre-aggregated snapshot
- Columns:

  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Category      | string   | Flow category |
  | Region        | string   | Region |
  | SKU           | string   | SKU |
  | HasConnection | bool     | Has connections |
  | LiveRatio     | string   | Activity class |
  | CustomerType  | string   | Customer type |
  | SegmentionType| string   | Segmentation |
  | CustomerCnt   | long     | Customer count |
  | Date          | datetime | Partition date |
  | ServiceType   | string   | Product |
  | Partition     | string   | 'Week' or 'Month' |

### Cached_Asrs_TopCustomersWoW_v2_Snapshot (signalrinsights.eastus2/SignalRBI)
- Represents: Week-over-week ranked customers by category/SKU with deltas.
- Class: Pre-aggregated snapshot
- Columns:

  | Column                    | Type     | Description |
  |---------------------------|----------|-------------|
  | P360_ID                   | string   | P360 ID |
  | P360_CustomerDisplayName  | string   | Name |
  | SKU                       | string   | SKU |
  | CustomerType              | string   | Type |
  | BillingType               | string   | Billing |
  | Category                  | string   | Metric category |
  | CurrentValue              | real     | Current value |
  | P360Url                   | string   | Link |
  | LastDay                   | datetime | Last day |
  | UsageType                 | string   | Usage type |
  | CurrentValue1             | real     | Auxiliary value |
  | PrevValue                 | real     | Previous |
  | W3Value                   | real     | 3-week value |
  | DeltaValue                | real     | Change |
  | Rank                      | long     | Rank |
  | W1Rank                    | long     | Rank week-1 |
  | W3Rank                    | long     | Rank week-3 |

### AwpsRuntimeRequestsGroups_Daily (signalrinsights.eastus2/SignalRBI)
- Represents: Daily aggregated runtime requests by category/metrics (AWPS).
- Class: Fact (daily)
- Columns:

  | Column       | Type     | Description |
  |--------------|----------|-------------|
  | Date         | datetime | Day |
  | Category     | string   | Category (e.g., RestApiScenario, Transport) |
  | Metrics      | string   | Scenario or metric identifier |
  | ResourceCount| long     | Unique resources |
  | RequestCount | long     | Requests |

### KPIv2019, KPI_AWPS, KPI_SocketIO (signalrinsights.eastus2/SignalRBI)
- Represents: KPI pre-aggregates by day.
- Class: Pre-aggregated
- Columns:

  | Column            | Type     | Description |
  |-------------------|----------|-------------|
  | Date              | datetime | Day |
  | SubscriptionCount | long     | Subscriptions |
  | ResourceCount     | long     | Resources |

### OKRv2021, OKRv2021_AWPS, OKRv2021_SocketIO (signalrinsights.eastus2/SignalRBI)
- Represents: OKR metrics by category and day.
- Class: Pre-aggregated
- Columns:

  | Column   | Type     | Description |
  |----------|----------|-------------|
  | Date     | datetime | Day |
  | Category | string   | OKR category |
  | Value    | real     | Value |

### ChurnCustomers_Monthly (signalrinsights.eastus2/SignalRBI)
- Represents: Monthly churn stats by service type.
- Class: Pre-aggregated (monthly)
- Columns:

  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Month         | datetime | Month |
  | ServiceType   | string   | Product |
  | Total         | long     | Total customers |
  | Churn         | long     | Churned |
  | Standard      | long     | Standard tier customers |
  | StandardChurn | long     | Standard churned |
  | RunDay        | datetime | Snapshot day |

### ConvertCustomer_Weekly (signalrinsights.eastus2/SignalRBI)
- Represents: Week-level conversions by path (free→paid/premium, etc.).
- Class: Pre-aggregated (weekly)
- Columns:

  | Column             | Type     | Description |
  |--------------------|----------|-------------|
  | Week               | datetime | Week |
  | ServiceType        | string   | Product |
  | FreeToStandard     | long     | Count |
  | TotalCustomers     | long     | Count |
  | StandardCustomers  | long     | Count |
  | RunDay             | datetime | Snapshot day |
  | FreeToPaid         | long     | Count |
  | StandardToPremium  | long     | Count |
  | FreeToPremium      | long     | Count |
  | PremiumCustomers   | long     | Count |

### ManageResourceTags (signalrinsights.eastus2/SignalRBI)
- Represents: Resource tag change operations via management plane.
- Class: Fact (daily)
- Columns:

  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Date          | datetime | Day |
  | SubscriptionId| string   | Subscription |
  | ResourceId    | string   | Resource |
  | RequestName   | string   | Operation |
  | Tags          | string   | Tag data |
  | Count         | long     | Ops count |

### SubscriptionRetentionSnapshot, CustomerRetentionSnapshot, ResourceRetentionSnapshot (signalrinsights.eastus2/SignalRBI)
- Represents: Retention snapshots with valid [StartDate, EndDate] windows.
- Class: Snapshot with ranges
- Columns:

  | Column         | Type     | Description |
  |----------------|----------|-------------|
  | SubscriptionId | string   | Subscription key (SubscriptionRetentionSnapshot) |
  | C360_ID        | string   | Customer key (CustomerRetentionSnapshot) |
  | ResourceId     | string   | Resource key (ResourceRetentionSnapshot) |
  | StartDate      | datetime | Cohort start |
  | EndDate        | datetime | Valid until |

### BoundTraffic_Daily (signalrinsights.eastus2/SignalRBI)
- Represents: Daily bound traffic metrics (e.g., OutboundTraffic).
- Class: Fact (daily)
- Columns:

  | Column        | Type     | Description |
  |---------------|----------|-------------|
  | Date          | datetime | Day |
  | Role          | string   | Resource/role |
  | Region        | string   | Region |
  | SubscriptionId| string   | Subscription |
  | Endpoint      | string   | Endpoint |
  | MetricName    | string   | Metric (e.g., OutboundTraffic) |
  | CustomerType  | string   | Customer type |
  | MessageCount  | long     | Count/volume |

### DeleteSurvey, DeleteSurveyWebPubSub (signalrinsights.eastus2/SignalRBI)
- Represents: Survey feedback after delete actions.
- Columns: Not provided in input.

### Requests, HttpIncomingRequests (armprodgbl.eastus/ARM)
- Represents: ARM incoming requests logs.
- Columns: Not provided in input.

### WebTools_Raw (ddtelinsights)
- Represents: VS tooling telemetry events.
- Columns: Not provided in input.

### RuntimeTransport_Daily, RuntimeTransport_EU_Daily (signalrinsights.eastus2/SignalRBI)
- Represents: Runtime transport telemetry (global and EU shard).
- Columns: Not provided in input.

## Views (Reusable Layers)
No reusable views were provided in the input. Some queries rely on user-defined functions (e.g., Unionizer(), DailyResource(), ResourceFlow_Weekly/Monthly, SubscriptionFlow_Weekly/Monthly, CustomerFlow_Weekly/Monthly, SignalRTeamInternalSubscriptionIds()). Refer to your ADX database for their definitions and parameters before use.

## Query Building Blocks (Copy-paste snippets)

- Time window template (day/week/month, effective end-time)
  ```kusto
  // Parameters
  let LookbackDays = 60d;
  let EndDate =
    toscalar(
      BillingUsage_Daily
      | where Date > ago(10d)
      | summarize RegionsReported = dcount(Region) by Date
      | where RegionsReported >= <MinRegions> // e.g., 2 for small gates, or 38 for global
      | top 1 by Date desc
      | project Date
    );
  // Daily window with gate
  <FactTable>
  | where Date > ago(LookbackDays) and Date <= EndDate
  ```

- Rolling window anchored to latest available day
  ```kusto
  let dateAnchor = toscalar(<FactTable> | top 1 by TimeCol desc | project TimeCol);
  <FactTable>
  | where TimeCol > ago(10d)
  | where TimeCol > dateAnchor - 7d
  | summarize <Metric> by Date = dateAnchor, Type = 'Rolling7'
  | union (
      <FactTable>
      | where TimeCol > ago(30d)
      | where TimeCol > dateAnchor - 28d
      | summarize <Metric> by Date = dateAnchor, Type = 'Rolling28'
    )
  ```

- Join template (normalize keys, common joins)
  ```kusto
  let fact = MaxConnectionCount_Daily
  | where Date >= startofweek(now(), -12) and Role has '/signalr/'
  | extend ResourceId = tolower(iif(Role has '/replicas/', substring(Role, 0, indexof(Role, '/replicas/')), Role));
  let settings = RPSettingLatest | extend ResourceId = tolower(ResourceId);
  let subs = SubscriptionMappings;
  fact
  | join kind=leftouter settings on ResourceId
  | join kind=inner subs on SubscriptionId
  | project-away SubscriptionId1, ResourceId1
  ```

- De-dup / latest-by pattern
  ```kusto
  <Table>
  | summarize arg_max(TimeCol, *) by <Key>
  ```

- Important filters (default exclusions and valid operations)
  ```kusto
  // Exclude internal/team subscriptions
  | where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())

  // Keep only valid RP ApiName set (SignalR)
  let validApi =
    ManageRPQosDaily
    | where Date > ago(30d)
    | where ApiName !in ('INVALID','GetResource','OperationList','OperationResult','UpdateSubscription')
           and ApiName !contains 'acs' and ApiName !contains 'acis'
           and CustomerType in ('SignalR','')
           and ApiName !in ('Internal-ACIS','UNCATEGORY')
    | distinct ApiName;
  ManageRPQosDaily
  | join kind=inner validApi on ApiName
  ```

- ID parsing/derivation
  ```kusto
  // Parse SubscriptionId from ARM ResourceId (pattern used in existing queries)
  | extend SubscriptionId = tostring(split(ResourceId, '/')[2])

  // Normalize Role to primary ResourceId (strip replicas)
  | extend ResourceId = iif(Role has '/replicas/', substring(Role, 0, indexof(Role, '/replicas/')), Role)
  | extend ResourceId = tolower(ResourceId)
  ```

- QoS computation templates
  ```kusto
  // Operation/Connectivity QoS
  | summarize UpTime = sum(totalUpTimeSec), TotalTime = sum(totalTimeSec) by <Groups>
  | extend Qos = iif(TotalTime == 0, 1.0, 1.0*UpTime/TotalTime)

  // SlaAttainment
  | summarize SlaAttainment = 1.0 * dcountif(ResourceId, Qos >= <Threshold>, 4) / dcount(ResourceId, 4) by <TimeBin>, <Dim>
  ```

- Revenue normalization with placeholders
  ```kusto
  let UnitPrice = pack('Free', 0.0, 'Standard', <UnitPrice_Standard>, 'Premium', <UnitPrice_Premium>, 'Other', <UnitPrice_Other>);
  BillingUsage_Daily
  | extend Price = todouble(coalesce(UnitPrice[SKU], UnitPrice['Other']))
  | extend Revenue = Price * Quantity
  ```

- Sharded union pattern (EU/global)
  ```kusto
  FeatureTrackV2_Daily
  | union FeatureTrackV2_EU_Daily
  | extend Date = startofday(Date), ResourceId = tolower(ResourceId)
  | summarize RequestCount = sum(RequestCount) by Date, Feature, Category, ResourceId, SubscriptionId
  ```

## Example Queries (with explanations)

1) SignalR Operation QoS with regional and overall SLA attainment
- Description: Computes QoS per day and region using OperationQoS_Daily, then derives SLA attainment as the fraction of resources meeting a threshold (0.999). Adapting: change window (ago(43d)), threshold, or replace env_cloud_location with another dimension.
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
    by Date, Region = 'Overall'
)
```

2) Rolling 7/28-day QoS anchored to the latest day (SignalR)
- Description: Anchors rolling windows to the most recent env_time in OperationQoS_Daily and computes QoS. Adapting: switch table to ConnectivityQoS_Daily or adjust 7/28 windows.
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

3) Weekly activity classification with connections and SKU (SignalR)
- Description: Joins MaxConnectionCount_Daily with BillingUsage_Daily to derive HasConnection and LiveRatio categories weekly. Adapting: change ActiveDays thresholds or replace Role filter to WebPubSub.
```kusto
MaxConnectionCount_Daily
| where Date >= startofweek(now(), -8) and SubscriptionId !in (SignalRTeamInternalSubscriptionIds()) and Role has '/signalr/'
| join kind = inner BillingUsage_Daily on $left.Role == $right.ResourceId, Date
| summarize Conn = max(MaxConnectionCount), SKU = max(SKU), Region = max(Region1), ActiveDays = dcount(Date) by Week = startofweek(Date), ResourceId
| project Week, ResourceId, Category = 'Total', Region, SKU, HasConnection = Conn > 0, LiveRatio = case(ActiveDays < 3, 'Swift', 'Occasional')
| summarize ResourceCnt = dcount(ResourceId, 3) by Week, Category, Region, SKU, HasConnection, LiveRatio
```

4) Billing normalized revenue by month (SignalR) with price placeholders
- Description: Calculates monthly normalized revenue by SKU and cohorts using a price map. Adapting: change Service, add more SKUs, or bucket by UsageType.
```kusto
let UnitPrice = pack('Free', 0.0, 'Standard', <UnitPrice_Standard>, 'Premium', <UnitPrice_Premium>, 'Other', <UnitPrice_Other>);
BillingUsage_Daily
| where Date >= startofmonth(now(), -16) and ResourceId has 'microsoft.signalrservice/signalr'
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
| join kind = inner SubscriptionMappings on SubscriptionId
| extend Price = todouble(coalesce(UnitPrice[SKU], UnitPrice['Other']))
| extend Revenue = Price * Quantity
| summarize BillingNormalizedRevenue = sum(Revenue) by DateKey = startofmonth(Date), SKU, CustomerType, BillingType
| extend UsageType = iif(CustomerType == 'Internal', CustomerType, BillingType)
```

5) Feature usage across shards with weekly aggregation (SignalR)
- Description: Unions global and EU FeatureTrack V2 tables, normalizes categories, excludes internal subs, joins usage to exclude message-only SKUs, and summarizes by week. Adapting: modify feature list/category mapping, add other filters.
```kusto
FeatureTrackV2_Daily
| union FeatureTrackV2_EU_Daily
| where Date > startofweek(now()) - 56d 
| project-away Properties
| extend Date = startofday(Date),
         Category = case(Feature in ('BlazorServerSide', 'Samples'), Feature,
                         Category endswith 'Ping', substring(Category, 8, indexof(Category, 'Ping') - 8), Category)
| where ResourceId has 'microsoft.signalrservice/signalr' and SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
| join kind = inner (BillingUsage_Daily | where SKU !in ('MessageCount', 'MessageCountPremium')) on Date, ResourceId
| summarize RequestCount = sum(RequestCount), SKU = max(SKU) by Week = startofweek(Date), Feature, ResourceId, SubscriptionId, Category
```

6) Manage RP QoS with valid ApiName cohort (SignalR)
- Description: Builds a valid ApiName cohort and computes daily QoS by region, with an overall union. Adapting: change cohort criteria or CustomerType to WebPubSub.
```kusto
let validApi = ManageRPQosDaily
| where Date > ago(43d) and ApiName !in ('INVALID', 'GetResource', 'OperationList', 'OperationResult', 'UpdateSubscription')
| where ApiName !contains 'acs' and ApiName !contains 'acis'
| where CustomerType in ('SignalR', '') and ApiName !in ('Internal-ACIS', 'UNCATEGORY')
| distinct ApiName;
ManageRPQosDaily
| where Date > ago(43d)
| join kind = inner validApi on ApiName
| summarize QoS = 1.0*sumif(Count, Result in ('Success','Timeout','CustomerError'))/sum(Count), TotalRequest = sum(Count) by Date, Region
| union (
  ManageRPQosDaily
  | where Date > ago(43d)
  | join kind = inner validApi on ApiName
  | summarize QoS = 1.0*sumif(Count, Result in ('Success','Timeout','CustomerError'))/sum(Count), TotalRequest = sum(Count) by Date, Region = 'Overall'
)
```

7) Effective end-date gate using multi-region coverage (WebPubSub)
- Description: Determines the last complete day where enough regions reported data and uses it to bound a daily resource count by SKU and activity. Adapting: change region set or threshold.
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
| where Date > ago(61d) and Date <= EndDate and ResourceId has 'microsoft.signalrservice/webpubsub'
| extend SubscriptionId = tostring(split(ResourceId, '/')[2])
| where SubscriptionId !in (SignalRTeamInternalSubscriptionIds())
| summarize SKU = max(SKU), Region = max(Region) by Date, ResourceId
| join kind = leftouter MaxConnectionCount_Daily on Date, $left.ResourceId == $right.Role
| extend HasConnection = iif(isempty(Role), false, MaxConnectionCount > 0)
| summarize Total = dcount(ResourceId) by Date, SKU, Region, HasConnection
```

8) Retention grid (monthly) using snapshots (Subscriptions)
- Description: Builds a retention matrix by cohort start month vs. months since start, using StartDate/EndDate windows and dcount distinct entity. Adapting: switch to Customer/Resource snapshots.
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

## Reasoning Notes (only if uncertain)
- Timezone: Not specified; we assumed UTC. If data was localized, regional days may straddle boundaries.
- Role vs. ResourceId: Many facts use Role as the resource path; we adopt normalizing Role to ResourceId and stripping '/replicas/'. This matches query patterns.
- SubscriptionId parsing: Existing queries use split(ResourceId, '/')[2]. While ARM paths often use '/subscriptions/<id>/', we follow the product’s pattern for consistency.
- Revenue prices: Queries include numeric multipliers per SKU. We adopt placeholders (<UnitPrice_Standard>, <UnitPrice_Premium>, etc.) to avoid hardcoding and to allow configuration.
- ManageRP QoS “good” results: For SignalR, good results include 'Success','Timeout','CustomerError'; for WebPubSub examples, only 'Success' is counted. We keep product-specific logic as-is per query context.
- Completeness thresholds: Examples use thresholds like 2 regions or 38 regions. Treat these as gates for coverage consistency; adjust for your reporting scope.
- EU shard unions: We assume schemas are identical across FeatureTrackV2_Daily and FeatureTrackV2_EU_Daily; normalize before summarizing to avoid duplication.
- Current-day inclusion: Many patterns anchor to latest available day using top 1; prefer gating to avoid partial-day effects.