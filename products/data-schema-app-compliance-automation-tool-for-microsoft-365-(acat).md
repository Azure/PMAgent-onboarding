# App Compliance Automation Tool for Microsoft 365 (ACAT) - Product and Data Overview Template

## 1. Product Overview

ACAT (App Compliance Automation Tool for Microsoft 365) is a service that enables Independent Software Vendors (ISVs) to generate, view, and manage compliance snapshots and reports for Microsoft 365 offers. This schema document compiles ACAT’s Kusto query playbook, data sources, conventions, and reusable patterns to support PMAgent in interpreting product-specific telemetry for adoption, health, and retention analyses.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**:
App Compliance Automation Tool for Microsoft 365 (ACAT)
- **Product Nick Names**: 
**[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations.
- **Kusto Cluster**:
https://acattelemetry.eastus.kusto.windows.net/
- **Kusto Database**:
Aggregation
- **Access Control**:
**[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed **groups/users** here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

# ACAT - Kusto Query Playbook

## Overview
- ACAT contains multiple Azure Data Explorer queries across several clusters to analyze ACAT adoption and health. The blocks include ISV Trend, HTTP Response, Snapshot success/failure and viewing, Compliance report flow, Active ISV vs. Guest, Error count, Azure Portal usage, and ISV retention/cohorting.
- Primary cluster/database:
  - Cluster: https://acattelemetry.eastus.kusto.windows.net/
  - Database: Aggregation
- Other referenced sources:
  - Cluster u360sec, database KPIData (Product360CustomerSubscriptions)
  - Cluster https://mcatprodkusto.westus3.kusto.windows.net/ (HttpResponse, Error, ACATTeamInternalTenantIds in GenevaDb)
  - Cluster https://azportalpartnerrow.westus.kusto.windows.net/ (ExtTelemetry)

## Conventions & Assumptions

### Time semantics
- Observed timestamp columns:
  - TIMESTAMP (primary across Aggregation, HttpResponse, ExtTelemetry)
  - PreciseTimeStamp (Error table)
  - Derived time buckets: hour = bin(TIMESTAMP, 1h), day = bin(TIMESTAMP, 1d), month-like cohorts via bin_at(..., 30d, anchor)
- Canonical Time Column: TIMESTAMP
  - Normalize other time columns to TIMESTAMP with project-rename before downstream summarization
    ```kusto
    // Normalize PreciseTimeStamp to canonical TIMESTAMP for consistency
    Error
    | project-rename TIMESTAMP = PreciseTimeStamp
    ```
- Typical windows and bins:
  - Filters: ago(7d), now(-14d), publicPreview anchors (e.g., datetime('2022-12-10'), datetime('2022-12-13'))
  - Bins: 1h, 1d, 30d (cohorting via bin_at with an anchor)
- Timezone: Not specified. Kusto stores times in UTC; assume UTC. Be cautious when interpreting “today” vs. “yesterday.”

### Freshness & Completeness Gates
- Ingestion cadence: Unknown for all tables. Current day may be incomplete.
- Recommended effective end time:
  - Use an effective end time that excludes the current partial day for daily aggregations.
    ```kusto
    let EffectiveEndTime = startofday(now()) - 1d;  // last full day
    let StartTime = EffectiveEndTime - 7d;
    Aggregation
    | where TIMESTAMP between (StartTime .. EffectiveEndTime)
    ```
- Multi-slice completeness gate pattern:
  - Choose a sentinel table and slice by a stable dimension (e.g., tenantId). Select the last day where the count of active slices meets a threshold.
    ```kusto
    let SentinelTable = Aggregation;
    let MinTenants = 100;  // tune for your use case
    let LastCompleteDay =
        SentinelTable
        | where TIMESTAMP > ago(30d)
        | summarize Tenants=dcount(tenantId) by Day = startofday(TIMESTAMP)
        | where Tenants >= MinTenants
        | top 1 by Day desc
        | project Day;
    // Use LastCompleteDay as the end of your window
    ```

### Joins & Alignment
- Frequent keys:
  - tenantId (primary entity), reportName, offerGuid
  - Customer_TenantId, Customer_TenantName, Customer_TenantDisplayName (enrichment from Product360CustomerSubscriptions)
- Typical join kinds:
  - inner (e.g., flow continuity post-GenSnapshotSucceeded)
  - leftouter (e.g., enrichment from customer catalog; preserving the event-side rows)
- Post-join hygiene:
  - After joins, duplicate columns often appear (e.g., tenantId1); standardize with coalesce and drop extras.
    ```kusto
    T1
    | join kind=leftouter T2 on tenantId
    | extend tenantId = coalesce(tenantId, tenantId1)
    | project-away tenantId1
    ```
  - Use project-rename to align column names before unions/joins.

### Filters & Idioms
- Internal/test exclusions:
  - Exclude internal tenants by !in (ACATTeamInternalTenantIds), sometimes referenced as a function call ACATTeamInternalTenantIds().
    ```kusto
    | where tenantId !in (cluster('mcatprodkusto.westus3.kusto.windows.net').database('GenevaDb').ACATTeamInternalTenantIds())
    ```
- String filters:
  - startswith for URI prefix grouping
  - endswith for action classification (Active ISV: action endswith "Sent")
  - has for substring exclusions (e.g., !has "Contoso")
- Null/empty checks:
  - isnotempty for offerGuid or tenantId presence

### Cross-cluster/DB & Sharding
- Cross-cluster qualification:
  ```kusto
  cluster('u360sec').database('KPIData').Product360CustomerSubscriptions
  cluster('mcatprodkusto.westus3.kusto.windows.net').database('GenevaDb').ACATTeamInternalTenantIds()
  cluster('azportalpartnerrow.westus.kusto.windows.net').database('<DB>').ExtTelemetry
  ```
- Union patterns:
  - For same-schema sources, normalize time and keys before summarize.
    ```kusto
    let S1 = cluster('X').database('D').Table | project TIMESTAMP, tenantId, colA;
    let S2 = cluster('Y').database('D').Table | project TIMESTAMP, tenantId, colA;
    union S1, S2
    | summarize Count = count() by bin(TIMESTAMP, 1d), tenantId
    ```

### Table classes
- Fact (events):
  - Aggregation: ACAT action events (GenSnapshotSucceeded, GetSnapshotAPICalled, CreateSucceeded, UpdateSucceeded, ReportDownloadedByAppCompliance)
  - HttpResponse: API call facts (httpMethod, targetUri, httpStatusCode)
  - ExtTelemetry: Azure Portal extension events (extension, action, data payload with reportName)
  - Error: Error events (errorType), time as PreciseTimeStamp
- Snapshot/Reference:
  - Product360CustomerSubscriptions: Tenant directory (Customer_TenantId/Name/DisplayName)
  - ACATTeamInternalTenantIds: Internal tenant allow/deny set (used for exclusion)

## Entity & Counting Rules (Core Definitions)

- Entity model:
  - tenant (tenantId) → report (reportName) → offer (offerGuid)
  - Enrichment: Customer_TenantId → Customer_TenantName/DisplayName
- Counting rules:
  - Unique ISVs: dcount(tenantId)
  - Active ISVs: dcountif(tenantId, action endswith "Sent") on ExtTelemetry for extension == "Microsoft_Azure_AppComplianceAutomation"
  - Guests: nISVs - nActiveISVs (as computed in queries)
  - Offer configuration: CreateSucceeded/UpdateSucceeded with non-empty offerGuid; split comma-separated values via mv-expand and trim whitespace before deduping
  - Viewing behavior: GetSnapshotAPICalled after GenSnapshotSucceeded; earliest viewed timestamp per tenant/report used to define onboarding
- Cohorts/Retention:
  - OnboardedAt: min(ViewedAt) per tenant based on earliest GetSnapshot after GenSnapshot; backfill rule for events pre-publicPreview anchored to the release date
  - Retention windows via bin_at(..., 30d, publicPreview) for cohort and activity alignment
- Do/Don’t:
  - Do deduplicate after mv-expand offerGuid before counting
  - Do filter internal tenants using ACATTeamInternalTenantIds
  - Don’t use current day for daily KPIs unless a freshness gate confirms completeness
  - Don’t join on non-normalized keys (trimmed, lower-cased if applicable) when IDs might have formatting variance

## Views (Reusable Layers)


## Query Building Blocks (Copy-paste snippets, contains snippets and description)

- Time window template
  - Description: Use an explicit start/end with an effective end time that avoids current-day partial ingestion.
  - Snippet:
    ```kusto
    // Time window with effective end time (avoid current day)
    let EffectiveEnd = startofday(now()) - 1d;
    let Start = EffectiveEnd - 7d;
    T
    | where TIMESTAMP between (Start .. EffectiveEnd)
    | summarize Count = count() by bin(TIMESTAMP, 1d)
    ```

- Join template (tenant-aligned, post-join hygiene)
  - Description: Align on tenantId/reportName, resolve duplicate columns, and preserve the event-side with leftouter when enriching.
  - Snippet:
    ```kusto
    let Tenants = cluster('u360sec').database('KPIData').Product360CustomerSubscriptions
                 | project Customer_TenantId, Customer_TenantName;
    Aggregation
    | join kind=leftouter Tenants on $left.tenantId == $right.Customer_TenantId
    | project-rename tenantName = Customer_TenantName
    | project-away Customer_TenantId
    ```

- De-dup pattern by “latest” or “earliest”
  - Description: Use arg_max/arg_min for latest or first occurrence per key.
  - Snippet:
    ```kusto
    // Latest record per tenant
    Aggregation
    | summarize arg_max(TIMESTAMP, *) by tenantId

    // Earliest configured offer per tenant/report
    T
    | summarize FirstAt = arg_min(TIMESTAMP, *) by tenantId, reportName
    ```

- Important filters (internal tenants, API path grouping, non-empty IDs)
  - Description: Standardize default exclusions and normalize API paths by prefix.
  - Snippet:
    ```kusto
    // Exclude internal/test tenants
    | where tenantId !in (cluster('mcatprodkusto.westus3.kusto.windows.net').database('GenevaDb').ACATTeamInternalTenantIds())

    // Normalize to a canonical API prefix group
    | extend targetAPI = iff(targetUri startswith '/providers/Microsoft.AppComplianceAutomation/reports/',
                             '/providers/Microsoft.AppComplianceAutomation/reports/',
                             targetUri)
    ```

- Important definitions
  - Description: Active ISV vs Guest on the portal extension telemetry.
  - Snippet:
    ```kusto
    cluster('azportalpartnerrow.westus.kusto.windows.net').database('<DB>').ExtTelemetry
    | where extension == "Microsoft_Azure_AppComplianceAutomation"
    | summarize
        nISVs = dcount(tenantId),
        nActiveISVs = dcountif(tenantId, action endswith "Sent")
      by day = bin(TIMESTAMP, 1d)
    | extend nGuests = nISVs - nActiveISVs
    ```

- ID parsing/derivation
  - Description: Extract reportName from ExtTelemetry.data JSON payload; normalize offerGuid lists.
  - Snippet:
    ```kusto
    // JSON extraction
    ExtTelemetry
    | extend reportName = tostring(parse_json(data)["reportName"])

    // Offer GUID list normalization
    Aggregation
    | where isnotempty(offerGuid)
    | mv-expand offerGuid = split(offerGuid, ',')
    | extend offerGuid = trim(@"\s", tostring(offerGuid))
    | where isnotempty(offerGuid)
    ```

- Sharded union (same-schema merge, then normalize)
  - Description: When combining same-schema sources across regions/clusters, normalize before summarize.
  - Snippet:
    ```kusto
    let A = cluster('C1').database('D').Aggregation | project TIMESTAMP, tenantId, Action;
    let B = cluster('C2').database('D').Aggregation | project TIMESTAMP, tenantId, Action;
    union A, B
    | summarize Events = count() by bin(TIMESTAMP, 1d), Action
    ```

## Example Queries (with explanations)

1) Adoption funnel and MoM progression (GenSnapshot → GetSnapshot → OfferConfigured → AppCompliance)
- Description: Builds progressive cohorts starting from GenSnapshotSucceeded, then the first GetSnapshot view, first offerGuid configuration (from Create/Update), and finally the first AppCompliance report request tied to configured offers. Each stage computes an accumulating series (daily) and joins stages to calculate MoM changes. It enriches tenant names and excludes a sample name. Adapt by changing publicPreview, adding internal-tenant filters, or changing the reporting window/bin.
```kusto
let publicPreview=datetime('2022-12-10');
let tenantInfo = cluster('u360sec').database('KPIData').Product360CustomerSubscriptions
| distinct Customer_TenantId, Customer_TenantName, Customer_TenantDisplayName;
let genSnapshot= Aggregation
| where  Action =='GenSnapshotSucceeded'
| join kind=leftouter  tenantInfo on $left.tenantId==$right.Customer_TenantId
| where  Customer_TenantName !has "Contoso"
| summarize  GeneratedAt=min(TIMESTAMP) by tenantId,reportName;
let backfillView=genSnapshot
| where  GeneratedAt <datetime('2022-12-13')
| extend  ViewedAt=GeneratedAt
| project-away GeneratedAt;
let acc_genSnapshot=genSnapshot
| summarize GeneratedAt=min(GeneratedAt) by tenantId
| make-series n=dcount(tenantId) on GeneratedAt from bin(publicPreview,1d) to now() step 1d
| mv-expand n,GeneratedAt
| extend GeneratedAt=todatetime(GeneratedAt)
| sort by GeneratedAt asc 
| serialize  acc_GeneratedAt=row_cumsum(toint(n))
| project-away n;
let getSnapshot=Aggregation
| where Action =='GetSnapshotAPICalled'
| join kind=inner  genSnapshot on tenantId,reportName
| where TIMESTAMP >GeneratedAt
| summarize  ViewedAt=min(TIMESTAMP) by tenantId,reportName
| union backfillView;
let acc_getSnapshot=getSnapshot
| summarize ViewedAt=min(ViewedAt) by tenantId
| make-series n=dcount(tenantId) on ViewedAt from bin(publicPreview,1d) to now() step 1d
| mv-expand n,ViewedAt
| extend ViewedAt=todatetime(ViewedAt)
| sort by ViewedAt asc 
| serialize  acc_ViewedAt=row_cumsum(toint(n))
| project-away n;
let createOfferGuid=Aggregation
| where  Action =='CreateSucceeded' and   isnotempty(offerGuid) ;
let updateOfferGuid=Aggregation
| where  Action =='UpdateSucceeded' and   isnotempty(offerGuid) ;
let offerGUID= union updateOfferGuid, createOfferGuid
| join kind=inner  getSnapshot on tenantId,reportName
| summarize ConfiguredofferGuidAt=min(TIMESTAMP) by tenantId,reportName,offerGuid
| summarize arg_max(ConfiguredofferGuidAt, *) by tenantId,reportName
| mv-expand offerGuid = split(offerGuid, ',')
| project tenantId,reportName,offerGuid = trim(@"\s", tostring(offerGuid)),ConfiguredofferGuidAt;
let acc_offerGuid=offerGUID
| summarize FirstConfiguredat=arg_min(ConfiguredofferGuidAt,*) by tenantId
| make-series n=dcount(tenantId) on FirstConfiguredat from bin(publicPreview,1d) to now() step 1d
| mv-expand n,FirstConfiguredat
| extend FirstConfiguredat=todatetime(FirstConfiguredat)
| sort by FirstConfiguredat asc 
| serialize  acc_FirstConfiguredat=row_cumsum(toint(n))
| project-away n;
let appCompliance = Aggregation
| where  Action =='ReportDownloadedByAppCompliance'
| join kind = leftouter offerGUID on $left.offerGuid == $right.offerGuid
| where isnotempty(tenantId1) and TIMESTAMP >ConfiguredofferGuidAt
| summarize ReportRequestedAt=min(TIMESTAMP) by tenantId1,reportName,offerGuid;
let acc_AppCompliance=appCompliance
| summarize FirstRequestedAt=arg_min(ReportRequestedAt,*) by tenantId1
| make-series n=dcount(tenantId1) on FirstRequestedAt from bin(publicPreview,1d) to now() step 1d
| mv-expand n,FirstRequestedAt
| extend FirstRequestedAt=todatetime(FirstRequestedAt)
| sort by FirstRequestedAt asc 
| serialize  acc_FirstRequestedAt=row_cumsum(toint(n))
| project-away n;
acc_genSnapshot
| join kind=leftouter acc_getSnapshot on $left.GeneratedAt==$right.ViewedAt
| join kind=leftouter acc_offerGuid on $left.ViewedAt==$right.FirstConfiguredat
| join kind=leftouter acc_AppCompliance on $left.FirstConfiguredat==$right.FirstRequestedAt
| serialize acc_ViewedAt
| extend MoM=todouble(acc_ViewedAt-prev(acc_ViewedAt,30))/prev(acc_ViewedAt,30)*100
| extend MoM=iff(isnull( MoM),0.0,MoM)
| sort by GeneratedAt desc
```

2) HTTP response distribution by API, hour, and status
- Description: Counts HttpResponse events over the last 7 days, excluding internal tenants, normalizing API path to a canonical prefix for AppComplianceAutomation reports, and bucketing by hour. Adapt by changing ago(7d) or adding more prefixes.
```kusto
HttpResponse
| where TIMESTAMP >ago(7d)  and tenantId !in (ACATTeamInternalTenantIds)
| extend  targetAPI=iff(targetUri startswith '/providers/Microsoft.AppComplianceAutomation/reports/','/providers/Microsoft.AppComplianceAutomation/reports/',targetUri), hour=bin(TIMESTAMP,1h)
| extend  targetAPIandMethod=strcat(httpMethod,' ',targetAPI)
| summarize count() by targetAPIandMethod,hour,httpStatusCode
```

3) HTTP response distribution (duplicate variant as provided)
- Description: Same as the previous query (kept to preserve all provided content). Use either instance interchangeably.
```kusto
HttpResponse
| where TIMESTAMP >ago(7d)  and tenantId !in (ACATTeamInternalTenantIds)
| extend  targetAPI=iff(targetUri startswith '/providers/Microsoft.AppComplianceAutomation/reports/','/providers/Microsoft.AppComplianceAutomation/reports/',targetUri), hour=bin(TIMESTAMP,1h)
| extend  targetAPIandMethod=strcat(httpMethod,' ',targetAPI)
| summarize count() by targetAPIandMethod,hour,httpStatusCode
```

4) HTTP response distribution (duplicate variant as provided)
- Description: Same as above; useful as a starting point to add additional filters (e.g., subscription, region) if present in your schema.
```kusto
HttpResponse
| where TIMESTAMP >ago(7d)  and tenantId !in (ACATTeamInternalTenantIds)
| extend  targetAPI=iff(targetUri startswith '/providers/Microsoft.AppComplianceAutomation/reports/','/providers/Microsoft.AppComplianceAutomation/reports/',targetUri), hour=bin(TIMESTAMP,1h)
| extend  targetAPIandMethod=strcat(httpMethod,' ',targetAPI)
| summarize count() by targetAPIandMethod,hour,httpStatusCode
```

5) Portal extension ISV activity: Active vs Guest
- Description: From ExtTelemetry, filters for the ACAT extension, excludes internal tenants (via function in GenevaDb) and computes daily distinct ISVs and Active ISVs (action endswith "Sent"). Guests are the remainder. Adapt by changing window or adding reportName extraction where needed.
```kusto
let tenantInfo = cluster('u360sec').database('KPIData').Product360CustomerSubscriptions 
| distinct Customer_TenantId, Customer_TenantName, Customer_TenantDisplayName;
ExtTelemetry
| where extension =="Microsoft_Azure_AppComplianceAutomation" and tenantId !in (cluster('mcatprodkusto.westus3.kusto.windows.net').database('GenevaDb').ACATTeamInternalTenantIds())
| extend reportName=tostring(parse_json(data)["reportName"]),day=bin(TIMESTAMP,1d)
| summarize nISVs=dcount(tenantId),nActiveISVs=dcountif(tenantId,action  endswith "Sent") by day
| extend nGuests=nISVs - nActiveISVs
```

6) Error hourly counts (normalize PreciseTimeStamp)
- Description: Counts error events hourly over the last 14 days. The original uses PreciseTimeStamp for filtering but bins TIMESTAMP. Prefer normalizing PreciseTimeStamp to TIMESTAMP for consistency.
```kusto
Error
| where PreciseTimeStamp >= now(-14d)
| extend  hourlyTime=bin(TIMESTAMP,1h)
| summarize count(),TimeStamp=min(TIMESTAMP) by errorType,hourlyTime
```

7) Error hourly counts (duplicate variant as provided)
- Description: Same as above; keep as a template for adding errorType allowlists/denylists.
```kusto
Error
| where PreciseTimeStamp >= now(-14d)
| extend  hourlyTime=bin(TIMESTAMP,1h)
| summarize count(),TimeStamp=min(TIMESTAMP) by errorType,hourlyTime
```

8) ISV retention/cohorting relative to public preview
- Description: Defines onboarding as the earliest report view after a successful snapshot (with backfill pre-publicPreview). Forms monthly cohorts (30d bins anchored at publicPreview) and counts tenants active in that period via lastActiveAt (last activity in Aggregation while excluding GenSnapshotSucceeded or post-publicPreview-only activity). Use this for cohort curves, changing publicPreview or bin size as needed.
```kusto
let publicPreview=datetime('2022-12-13'); let genSnapshot= Aggregation |where  Action =='GenSnapshotSucceeded' | where tenantId !in ("972de77a-552f-45ca-96ef-0b3d91110db4", "800398a7-3ef1-41fe-824a-687dc6e0b1d9", "49511fb1-4af8-4eb3-a4f3-0a1b3038b64d", "46fbc19c-18f2-4c28-b879-c08e01afd40f", "6a1c431e-7372-45c4-a780-555e7ae1a2ac", "217e0081-c272-40b1-921c-94745eba0eed", "b16461d0-d7eb-46c1-b3c1-86f2a55c9042", "e947416c-06b4-4fa6-9889-aeea22e44139", "ef05883f-b8b3-4031-8ffc-1dc84f621dff", "bbdddcf8-f6b5-4d8b-aa8b-8db0c66d0c6a", "f70e581e-768a-4fd4-b088-7540530f8377", "b2c0b6ec-0036-4fe9-b222-f419713a4772", "06f05128-8a81-4bc7-95e8-81e3de737730", "b80aed20-39d5-494e-aa1d-15ad0a398251", "e6fb4586-2f1f-45af-9af8-a5a101a6c3de", "a8667cb7-9598-42ad-b1af-37fa62890999", "f765057c-99a1-48ca-8149-00c006fba601") | summarize  GeneratedAt=min(TIMESTAMP) by tenantId,reportName; let backfillView=genSnapshot |where  GeneratedAt <publicPreview |extend  ViewedAt=GeneratedAt|project-away GeneratedAt; let ISVonboard=Aggregation |where Action =='GetSnapshotAPICalled' | join kind=inner  genSnapshot on tenantId,reportName |where TIMESTAMP >GeneratedAt | summarize  ViewedAt=min(TIMESTAMP) by tenantId,reportName | union backfillView | summarize  OnboardedAt=min(ViewedAt) by tenantId; Aggregation | where  Action !="GenSnapshotSucceeded" or TIMESTAMP<=publicPreview | summarize  arg_max(TIMESTAMP,*) by tenantId |extend lastActiveAt=TIMESTAMP | join kind=inner  ISVonboard on tenantId | make-series nISVs=count() on bin_at(lastActiveAt,30d,publicPreview) from publicPreview-30d to bin_at(now()+30d,30d,publicPreview) step 30d by bin_at(OnboardedAt,30d,publicPreview) | mv-expand  nISVs,lastActiveAt | extend  lastActiveAt=todatetime(lastActiveAt),nISVs=toint(nISVs) | where  lastActiveAt >=OnboardedAt | extend Nago=toint(format_timespan(lastActiveAt-OnboardedAt, 'd')) | sort by OnboardedAt,lastActiveAt | serialize acc=row_cumsum(nISVs,OnboardedAt !=prev(OnboardedAt))
```

## Reasoning Notes (only if uncertain)
- Timestamp timezone: Not specified; we adopt UTC because Kusto uses UTC by default.
- Internal tenant list: Sometimes referenced as a table and sometimes as a function (ACATTeamInternalTenantIds vs ACATTeamInternalTenantIds()). We assume both point to the same allow/deny set in GenevaDb and use the function form for safety.
- Customer directory enrichment (Product360CustomerSubscriptions) is treated as a reference snapshot; exact refresh cadence is not provided.
- AppCompliance linkage via offerGuid assumes offerGuid normalization (trim, split by comma). If upstream always provides single GUIDs, mv-expand still safely handles them.
- Retention bin of 30 days is used as “monthly” approximation per the provided queries; if calendar months are required, switch to bin(Time, 1mo).
- Freshness/completeness: Since ingestion delay is unknown, we recommend excluding the current day and optionally enforcing a tenant-count sentinel gate to avoid partial-day bias.
- Error table time normalization: The original queries filter on PreciseTimeStamp but bin on TIMESTAMP; we recommend renaming PreciseTimeStamp to TIMESTAMP for consistent processing.

## Canonical Tables

### Table name: cluster("acattelemetry.eastus.kusto.windows.net").database("Aggregation").Aggregation
- Priority: Normal
- What this table represents: Event-level telemetry produced by ACAT service components. Rows are facts (not pre-aggregated) describing actions such as GenSnapshotSucceeded, GetSnapshotAPICalled, CreateSucceeded, UpdateSucceeded, and ReportDownloadedByAppCompliance. Zero rows over a period likely mean no activity (not deletion).
- Freshness expectations: Unknown. Queries commonly use daily and hourly bins; be cautious with same-day data due to possible ingestion delay.
- When to use / When to avoid:
  - Use for adoption/retention funnels: snapshot generation → snapshot view → offer GUID configuration → App Compliance report requests.
  - Use to measure first-time events per tenant (e.g., first snapshot, first report download).
  - Use to build cumulative “acc” series via make-series and row_cumsum for growth tracking.
  - Avoid joining without narrowing time windows; the dataset can be large.
  - Avoid relying on join-introduced suffixed columns (e.g., tenantId1) as canonical fields; prefer disambiguated projections/renames.
- Similar tables & how to choose:
  - Error (MCAT): for service error trends rather than ACAT action telemetry.
  - HttpResponse (MCAT): for API-level request/response analysis; Aggregation is better for domain actions.
- Common Filters:
  - Time: TIMESTAMP with bins (1d, 1h) and explicit publicPreview cutoffs.
  - Action: specific values (GenSnapshotSucceeded, GetSnapshotAPICalled, CreateSucceeded, UpdateSucceeded, ReportDownloadedByAppCompliance).
  - Tenant: tenantId, often excluding internal tenants via ACATTeamInternalTenantIds.
  - Resource: reportName, offerGuid (may contain comma-separated list; split then trim).
- Table columns:
  | Column           | Type     | Description or meaning |
  |------------------|----------|------------------------|
  | PreciseTimeStamp | datetime | Ingestion/record precise time; use for fine-grained ordering if needed. |
  | TIMESTAMP        | datetime | Event occurrence time; primary for time filters and binning. |
  | reportName       | string   | Report identifier associated with snapshot/report operations. |
  | offerGuid        | string   | Offer GUID(s) configured; may be comma-separated and requires split/trim. |
  | tenantId         | string   | Customer tenant identifier; key for joins and distinct counts. |
  | Action           | string   | Event type (e.g., GenSnapshotSucceeded, GetSnapshotAPICalled, CreateSucceeded). |
- Column Explain:
  - TIMESTAMP: use for time windows and make-series; aligns event occurrence across stages.
  - Action: drives scenario scoping (generation vs view vs configuration vs report request).
  - tenantId: core segmentation key; combine with exclusion lists for internal tenants.
  - reportName: disambiguates multi-report behaviors per tenant.
  - offerGuid: used to link configuration actions to downstream App Compliance report requests.
  - PreciseTimeStamp: optional for tie-breaking or ingestion-order analyses.

---

### Table name: cluster("u360sec").database("KPIData").Product360CustomerSubscriptions
- Priority: Normal
- What this table represents: Snapshot-like reference of customer subscription metadata used for enriching telemetry with customer tenant information.
- Freshness expectations: Unknown; treat as periodically refreshed. If you need up-to-date display names, confirm dataset recency.
- When to use / When to avoid:
  - Use to join Aggregation events to Customer_TenantName/DisplayName for reporting.
  - Use to filter out specific named customers (e.g., excluding “Contoso”).
  - Avoid heavy fan-out joins without distinct pre-projection; use distinct on tenant keys before joining.
- Similar tables & how to choose:
  - None identified in input; this is the referenced customer substrate for enrichment.
- Common Filters:
  - Typically none; used in distinct projection then joined by Customer_TenantId (= tenantId).
- Table columns (from query usage; full schema not accessible here):
  | Column                   | Type    | Description or meaning |
  |--------------------------|---------|------------------------|
  | Customer_TenantId        | string  | Customer tenant AAD ID; join key to telemetry tenantId. |
  | Customer_TenantName      | string  | Tenant name; used for labeling and exclusions. |
  | Customer_TenantDisplayName | string | Human-friendly display name. |
- Column Explain:
  - Customer_TenantId: join to Aggregation.tenantId to append names.
  - Customer_TenantName/DisplayName: for reporting clarity and targeted exclusions.

---

### Table name: cluster("mcatprodkusto.westus3.kusto.windows.net").database("<unknown>").HttpResponse
- Priority: Normal
- What this table represents: API request/response telemetry (request method, target URI, status code) for ACAT endpoints within MCAT environment.
- Freshness expectations: Unknown; queries use 7-day hourly bins.
- When to use / When to avoid:
  - Use to analyze API usage by route/method and status code trends.
  - Use to isolate high-error endpoints by httpStatusCode over time.
  - Avoid mixing internal tenants; exclude ACATTeamInternalTenantIds.
  - Avoid raw high-cardinality URIs; normalize route prefixes (e.g., startswith for “/providers/Microsoft.AppComplianceAutomation/reports/”).
- Similar tables & how to choose:
  - Error (MCAT): for summarized error types; HttpResponse is more granular at request level.
  - Aggregation (ACAT): for domain actions rather than raw HTTP patterns.
- Common Filters:
  - Time: TIMESTAMP > ago(7d), hourly binning.
  - Tenant: tenantId !in (ACATTeamInternalTenantIds).
  - Route: targetUri normalization using startswith; build targetAPI and targetAPIandMethod.
  - Status: httpStatusCode segmentation.
- Table columns (from query usage; full schema not accessible here):
  | Column         | Type     | Description or meaning |
  |----------------|----------|------------------------|
  | TIMESTAMP      | datetime | Request time. |
  | tenantId       | string   | Requesting tenant; filter out internal tenants. |
  | targetUri      | string   | Request path; normalize to route families. |
  | httpMethod     | string   | HTTP verb (GET/POST/PUT/DELETE). |
  | httpStatusCode | int      | Response status code (e.g., 200, 4xx, 5xx). |
- Column Explain:
  - targetUri + httpMethod: combine into canonical endpoint identifier for trend splits.
  - httpStatusCode: use for success/failure slices.
  - tenantId: exclude internal traffic for external usage view.

---

### Table name: cluster("mcatprodkusto.westus3.kusto.windows.net").database("GenevaDb").ACATTeamInternalTenantIds
- Priority: Normal
- What this table represents: Internal tenant allow/block list used to exclude Microsoft internal or test tenants from public usage metrics. Often exposed as a function returning the set of tenant IDs.
- Freshness expectations: Unknown; treat as reference list that changes occasionally.
- When to use / When to avoid:
  - Use in NOT IN filters to remove internal traffic from HttpResponse/ExtTelemetry/Aggregation.
  - Use cross-cluster reference when running from non-MCAT clusters.
  - Avoid using as a join target; use as scalar set in in()/!in() for performance.
- Similar tables & how to choose:
  - None identified; this is the standard internal tenant list for filtering.
- Common Filters:
  - Used as a filter predicate: tenantId !in (ACATTeamInternalTenantIds) or cross-cluster function call variant.
- Table columns (from usage; this may be a function returning a set; schema not accessible here):
  | Column   | Type   | Description or meaning |
  |----------|--------|------------------------|
  | tenantId | string | Internal/team tenant IDs to exclude. |
- Column Explain:
  - tenantId: apply in exclusion predicates across all metrics to represent external ISV behavior.

---

### Table name: cluster("azportalpartnerrow.westus.kusto.windows.net").database("<unknown>").ExtTelemetry
- Priority: Normal
- What this table represents: Extension telemetry emitted by Azure Portal extension “Microsoft_Azure_AppComplianceAutomation”. Rows are per-event facts with extension payload.
- Freshness expectations: Unknown; queries use daily bins.
- When to use / When to avoid:
  - Use to count active ISVs (action endswith "Sent") vs total ISVs by day.
  - Use for portal engagement metrics specific to the ACAT extension.
  - Avoid including internal tenants; filter using ACATTeamInternalTenantIds from MCAT cluster.
  - Avoid unbounded parse_json over large windows; pre-filter by extension and time.
- Similar tables & how to choose:
  - Aggregation: ACAT backend action telemetry; ExtTelemetry focuses on portal-side events.
  - HttpResponse: API traffic; ExtTelemetry is UI/extension telemetry.
- Common Filters:
  - Time: TIMESTAMP with 1d bins.
  - Tenant: tenantId exclusion via cross-cluster internal list.
  - Extension: extension == "Microsoft_Azure_AppComplianceAutomation".
  - Payload fields: data JSON with reportName and action suffix "Sent".
- Table columns (from query usage; full schema not accessible here):
  | Column     | Type     | Description or meaning |
  |------------|----------|------------------------|
  | TIMESTAMP  | datetime | Event time; bin to 1d. |
  | extension  | string   | Portal extension identifier; filter equals ACAT extension name. |
  | tenantId   | string   | Customer tenant identifier. |
  | data       | dynamic  | JSON payload; contains reportName and other event metadata. |
  | action     | string   | Event action; used with endswith "Sent" to infer active ISVs. |
- Column Explain:
  - extension: hard filter to ACAT extension scope.
  - action: determines “active” vs “guest” counts.
  - data.reportName: extract via parse_json for per-report engagement.

---

### Table name: cluster("mcatprodkusto.westus3.kusto.windows.net").database("<unknown>").Error
- Priority: Normal
- What this table represents: Service error telemetry with typed error categories over time. Rows are facts; summarized at query time.
- Freshness expectations: Unknown; queries use rolling 14-day, hourly bins.
- When to use / When to avoid:
  - Use to trend errorType over time and identify spikes.
  - Use to correlate hourly error peaks with API issues (compare with HttpResponse).
  - Avoid using without time narrowing; error volumes can be high.
- Similar tables & how to choose:
  - HttpResponse: request/response status trends; Error focuses on categorized errors.
  - Aggregation: domain action telemetry; not for error diagnostics.
- Common Filters:
  - Time: PreciseTimeStamp >= now(-14d); hourly bin on TIMESTAMP.
  - Grouping: errorType, hourlyTime.
- Table columns (from query usage; full schema not accessible here):
  | Column           | Type     | Description or meaning |
  |------------------|----------|------------------------|
  | PreciseTimeStamp | datetime | Precise event timestamp; used for time filter windows. |
  | TIMESTAMP        | datetime | Event occurrence time; binned to 1h. |
  | errorType        | string   | Error category/type used for aggregation. |
- Column Explain:
  - errorType: primary breakdown for error monitoring.
  - PreciseTimeStamp vs TIMESTAMP: filter on PreciseTimeStamp, bin on TIMESTAMP for consistent buckets.

---

Guidance across tables
- Time windows: Default to smaller windows (7–14 days) and bin appropriately (1h or 1d). Expand after validating performance.
- Tenant hygiene: Always exclude internal tenants using ACATTeamInternalTenantIds to represent external ISV behavior.
- Stage funnels: For adoption/retention metrics, use earliest event per tenant per stage and build cumulative series with make-series + row_cumsum.
- Join practices: Use distinct and project-away to minimize column duplication; be mindful of auto-suffixed columns after joins.
- Current-day caution: Freshness/ingestion delay is unknown; avoid relying solely on “today” without verification.