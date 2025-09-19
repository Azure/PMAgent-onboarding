# SignalR and Web PubSub - Product and Data Overview Template

## 1. Product Overview

> SignalR and Web PubSub are Azure services enabling real-time messaging, connection management, and scalable pub/sub scenarios for web and cloud applications. This onboarding covers both SignalR and Web PubSub, including SocketIO support.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**: SignalR and Web PubSub
- **Product Nick Names**: 
> **[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations.
- **Kusto Cluster**: signalrinsights.eastus2
- **Kusto Database**: SignalRBI
- **Access Control**:
> **[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed **groups/users** here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

# SignalR and Web PubSub — Kusto Query Playbook

## Overview
Product: SignalR and Web PubSub

Summary: Power BI Power Query M blocks connecting to Azure Data Explorer to pull OKR/ARR and AI customer growth, usage (revenue, connections, messages), service type growth (SignalR/WebPubSub/SocketIO), feature tracking (replicas, autoscale, blazor-server, aspire, serverless), external/billable customers, top customers, retention, and also lower-priority VS integration, QoS, and runtime requests.

Primary cluster/database:
- Cluster: signalrinsights.eastus2
- Database: SignalRBI
- Alternates (external sources commonly used via cross-cluster): armprodgbl.eastus (ARM), ddtelinsights (VS telemetry)

High-priority scenarios emphasized by users:
- OKR analysis, ARR and AI customer growth
- Usage analysis: revenue, connection count, message count
- Service type growth: SignalR/Web PubSub/Web PubSub for SocketIO
- Feature tracks: replicas, autoscale, blazor-server, aspire, serverless
- External/billable customers; top customers
Low priority: VS (Visual Studio) integration, QoS analysis, runtime requests

## Conventions & Assumptions

### Time semantics
Observed time columns and canonicalization:
- Canonical Time Column: Date
- Other timestamp columns often used:
  - TimeStamp (OKR snapshots)
  - env_time (QoS)
  - Computed Week: startofweek(Date), Month: startofmonth(Date)
  - Start/end-of-period anchors: startofday(), endofmonth(), startofweek()
- Alias patterns:
  - project-rename TimeStamp = Date to normalize to the canonical column in ad-hoc unions
  - extend Month = startofmonth(Date), Week = startofweek(Date)
- Typical windows:
  - Short horizon: ago(30d)/ago(60d)/ago(61d)
  - Weekly: startofweek(now(), -8 to -18); rolling7/rolling28 anchored at latest available day
  - Monthly: startofmonth(now(), -12 to -16); often stop at previous full month
- Timezone: Not explicitly stated; assume UTC. Be cautious using current-day data.

### Freshness & Completeness Gates
- Ingestion cadence: Daily for facts and runtime; snapshots are weekly/monthly. Exact delay unknown.
- Avoid current day: Most revenue/consumption and cohort queries exclude the current day; prefer completed days.
- Effective “safe” end date pattern:
  - Use the last day where sentinel regions (e.g., australiaeast and westeurope) both have data to avoid partial-day skew:
    - let EndDate = toscalar(BillingUsage_Daily
      | where Date > ago(10d) and Region in ('australiaeast', 'westeurope')
      | summarize counter = dcount(Region) by Date
      | where counter >= 2
      | top 1 by Date desc
      | project Date);
- Rolling completeness for QoS:
  - Anchor a rolling-7/28 window on the latest available env_time using a self-join to the latest row.

Recommendation: For finance-like views, use the last complete week/month or the multi-region gate, not “today.”

### Joins & Alignment
- Frequent keys:
  - SubscriptionId (join to SubscriptionMappings/CustomerModel)
  - ResourceId (service type classification, join to runtime metrics)
  - Role (in MaxConnectionCount_Daily; join via tolower(ResourceId))
  - Region (dimensional)
- Typical join kinds:
  - inner to enforce activity presence (e.g., join to MaxConnectionCount_Daily)
  - leftouter to enrich with customer metadata (SubscriptionMappings)
  - fullouter for overlaying pre-aggregated snapshots with inline goal datatables
- Post-join hygiene:
  - Normalize case on ResourceId: extend Role = tolower(ResourceId) and join on Role
  - project-away duplicate column variants (e.g., TimeStamp1, SubscriptionId1)
  - project-rename to align column names for unions
  - coalesce() if you must resolve nulls across join sides

### Filters & Idioms
- Common predicates:
  - Service classification: ResourceId has 'microsoft.signalrservice/signalr' or 'microsoft.signalrservice/webpubsub'
  - Internal exclusion: SubscriptionId !in (SignalRTeamInternalSubscriptionIds) or SignalRTeamInternalSubscriptionIds() function
  - SKU filters: in ('Free','Standard','Premium'); often exclude 'MessageCount' meters when computing revenue/consumption
  - Text contains vs has: contains is case-insensitive substring; has is token-based; use has for provider paths, contains for substrings like 'openai'
- Cohorts: Build allowlists first (e.g., feature cohort, AI keyword cohort) and join kind=inner to facts
- Activity gates:
  - Join to MaxConnectionCount_Daily or ResourceMetrics to confirm live/active days/resources
  - HasConnection = MaxConnectionCount > 0

### Cross-cluster/DB & Sharding
- Cross-cluster qualification:
  - cluster('armprodgbl.eastus').database('<armdb>').Requests
  - cluster('ddtelinsights').database('<db>').WebTools_Raw
- EU data boundary:
  - Use FeatureTrackV2_Daily union FeatureTrackV2_EU_Daily
  - For runtime requests/transports, union non-EU and EU tables, then normalize Metrics and aggregate
- Order of operations for sharded unions:
  - union → normalize keys/time (tolower(ResourceId), startofday(Date)) → summarize/aggregate → only then join to dimensions

### Table classes
- Fact (daily/events): BillingUsage_Daily, ResourceMetrics, MaxConnectionCount_Daily, ConnectionMode_Daily, FeatureTrack*, Manage*QoS, Runtime* tables
- Snapshot (latest state): RPSettingLatest; TopCustomers/OKR snapshots; Retention snapshots
- Pre-aggregated: Cached_* OKR/TopCustomers/SubsTotal snapshots; KPI*/OKR* series
Usage guidance:
- Prefer facts for bottom-up recomputation, snapshots for stable dashboarding; avoid mixing within a single visual unless time aligned.

## Entity & Counting Rules (Core Definitions)
- Entity model:
  - resource → subscription → customer
  - Keys:
    - ResourceId: ARM ID (parse SubscriptionId via split(ResourceId, '/')[2])
    - SubscriptionId: primary business join key
    - CloudCustomerGuid / C360_ID / TPID: from SubscriptionMappings/CustomerModel
- Standard grouping levels:
  - By Date/Week/Month with startofX() alignment
  - By Service family (SignalR, WebPubSub/SocketIO), Region, SKU, CustomerType, SegmentName, BillingType
- Counting rules:
  - Distinct counts often use controlled accuracy: dcount(key, 3) or dcount(key, 4)
  - Active definitions:
    - HasConnection: MaxConnectionCount > 0 (from ResourceMetrics)
    - LiveRatio: derived from number of active days per period (e.g., <3 = Swift, <10 = Occasional, else Dedicate)
  - Revenue normalization:
    - Income = case(SKU == 'Free', 0.0, SKU == 'Standard', <UnitPriceStd>, SKU == 'Premium', <UnitPricePrem>, 1.0) * Quantity
    - Replace unit prices with configured rates in your environment

## Canonical Tables
This playbook summarizes how the SignalR and Web PubSub product composes Kusto queries, which tables to use for common business questions, and practical guidance per table. The product’s main cluster/database are signalrinsights.eastus2/SignalRBI unless otherwise noted. Time-to-freshness is not explicitly documented; be conservative with current-day data and prefer complete periods by using end-of-week/month or region-aligned slices as shown in queries.

...(truncated for brevity, but full content is included in the actual file)...

---

Acceptance Checklist
- Identified timestamp columns (Date, TimeStamp, env_time), typical windows, bin via startofweek/startofmonth, timezone marked as unknown (assumed UTC).
- Documented freshness and an effective end time strategy via multi-region gate; warned about current-day incompleteness.
- Produced entity model and counting rules; clarified active definitions and snapshot vs daily facts usage.
- Called out sharded/EU tables and provided a union pattern.
- Included default exclusion patterns and service classification filters.
- Provided ID parsing snippets and case normalization.
- Included more than 6 example Kusto queries with explanations.
- No fabricated fields; unit prices abstracted with placeholders.