# App Compliance Automation Tool for Microsoft 365 (ACAT) - Product and Data Overview Template

## 1. Product Overview

> Draft onboarding for App Compliance Automation Tool for Microsoft 365 (ACAT). This document defines product context and preserves the provided Kusto Query Playbook for PMAgent to reason over ACAT telemetry and metrics.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**:
> App Compliance Automation Tool for Microsoft 365 (ACAT)
- **Product Nick Names**: 
> **[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations.
- **Kusto Cluster**:
> acattelemetry.eastus.kusto.windows.net
- **Kusto Database**:
> Aggregation
- **Access Control**:
> **[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed **groups/users** here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

# App Compliance Automation Tool for Microsoft 365 (ACAT) - Kusto Query Playbook

## Overview
- App Compliance Automation Tool for Microsoft 365 (ACAT) queries cover ISV onboarding trends, HTTP responses, snapshot generation and viewing, compliance report requests, active ISV vs. guest counts, error telemetry, Azure Portal extension usage, and ISV retention/cohorts.
- Primary cluster: https://acattelemetry.eastus.kusto.windows.net/
- Primary database: Aggregation

## Conventions & Assumptions

### Time semantics
- Canonical Time Column: TIMESTAMP
  - Other time columns observed:
    - PreciseTimeStamp (Error table; use when you need higher precision)
    - Derived aliases: GeneratedAt, ViewedAt, ReportRequestedAt, ConfiguredofferGuidAt, FirstConfiguredAt, FirstRequestedAt, lastActiveAt (created via summarize/extend/make-series).
  - Aliasing pattern:
    - Use project-rename when normalizing to a canonical name:
      - Example: | project-rename TimeCol = TIMESTAMP
- Typical windows:
  - Short windows: ago(7d), now(-14d) for recent activity.
  - Longer cumulative trends: from a fixed anchor (publicPreview) to now() with 1d steps; 30d bin_at() for cohort analysis.
- Binning:
  - Hourly: bin(TIMESTAMP, 1h)
  - Daily: bin(TIMESTAMP, 1d)
  - Monthly-ish cohorts: bin_at(<time>, 30d, <anchor>)
- Timezone:
  - Not specified; assume UTC (Kusto datetimes are UTC). Be careful using “today” until ingestion completeness is confirmed.

### Freshness & Completeness Gates
- Ingestion cadence is not specified. Current-day data may be incomplete.
- Recommended strategies:
  - Default to excluding current day in daily analyses: let EffectiveEnd = startofday(ago(0d)); then filter TIMESTAMP < EffectiveEnd.
  - Minimum-activity gate per slice (tenants/day) to ensure completeness.

Multi-slice completeness gate template:
- Find last full day with ≥ <MinTenants> distinct tenants emitting events:
  - Use Aggregation as sentinel source (replace with HttpResponse/Error if that’s a stronger signal for your scenario).

### Joins & Alignment
- Frequent keys:
  - tenantId (primary entity key)
  - reportName (report-level join/grain)
  - offerGuid (comma-separated list; expand before joins)
  - Customer_TenantId (from Product360; tenant dimension)
- Common join kinds:
  - inner (to enforce presence, e.g., onboarding tied to snapshot)
  - leftouter (to enrich with dimension or keep left records)
- Post-join hygiene:
  - Resolve column name clashes using project-rename.
  - Drop unused columns with project-away.
  - Use coalesce() across alternative sources if the same attribute may come from multiple places.

### Filters & Idioms
- Internal/test tenant exclusion:
  - tenantId !in (ACATTeamInternalTenantIds) or via a cross-cluster function/table.
  - Explicit denylist of GUIDs often used for one-off analyses.
- String ops:
  - startswith() to collapse similar API endpoints to a prefix.
  - endswith() for action suffix checks (e.g., “Sent”).
  - parse_json() for extracting fields from dynamic payloads.
  - split()/mv-expand/trim() for multi-value attributes (offerGuid).
- Cohorts:
  - Build allowlists first (e.g., onboarded tenants), then join kind=inner to restrict downstream analysis.

### Cross-cluster/DB & Sharding
- Qualification patterns:
  - cluster('<fqdn>').database('<db>').<TableOrFunction>()
- Observed cross-cluster usage:
  - u360sec/KPIData → Product360CustomerSubscriptions (tenant dimension)
  - mcatprodkusto.westus3/GenevaDb → ACATTeamInternalTenantIds (function/table), GenerateSnapshot (in comments)
  - azportalpartnerrow.westus → ExtTelemetry (Azure Portal extension)
- If same-schema data exists in multiple shards/regions, use:
  - union → normalize keys and TIMESTAMP → summarize

### Table classes
- Fact/event:
  - Aggregation (ACAT product signals, includes Action, tenantId, reportName, offerGuid)
  - HttpResponse (API calls and statuses)
  - Error (errorType and timestamps)
  - ExtTelemetry (portal extension usage with action, data)
- Dimension/reference:
  - Product360CustomerSubscriptions (tenant metadata: name, display name)
  - ACATTeamInternalTenantIds (internal/test tenant list; appears as function in one query)

## Entity & Counting Rules (Core Definitions)

- Entity model:
  - Tenant (tenantId) → Report (reportName) → Offer (offerGuid)
  - Groupings:
    - By tenantId for ISV counts, onboarding, retention
    - By reportName for report-level funnels
    - By httpStatusCode, api/method for API telemetry
- Business definitions (from queries):
  - OnboardedAt: Earliest time a tenant views a report (GetSnapshotAPICalled) after a successful snapshot (GenSnapshotSucceeded), with backfill using snapshot time for pre-publicPreview.
  - Active ISVs (ExtTelemetry): action endswith "Sent".
  - Guests: nISVs - nActiveISVs (daily), where nISVs = dcount(tenantId) and nActiveISVs = dcountif(tenantId, action endswith "Sent").
  - Offer configured: First time a CreateSucceeded/UpdateSucceeded with non-empty offerGuid is associated to a tenant/report, expanding multiple GUIDs when present.

Counting Do/Don’t:
- Do deduplicate with summarize arg_min/arg_max by the proper key (tenantId, reportName).
- Do expand multi-value offerGuid before counting.
- Don’t mix snapshot-first and view-first without enforcing ordering (TIMESTAMP > GeneratedAt).
- Don’t include internal/test tenants unless explicitly requested.

## Views (Reusable Layers)

- Important definitions (Onboarding, Active/Guest, Offer configured)
  - Description: Reusable definitions to align metrics across queries.
  - Snippet:
    ```kusto
    // Onboarding: earliest view after snapshot (with backfill pre-publicPreview)
    let publicPreview = datetime(2022-12-13);
    let genSnapshot =
        Aggregation
        | where Action == "GenSnapshotSucceeded"
        | summarize GeneratedAt = min(TIMESTAMP) by tenantId, reportName;
    let backfillView =
        genSnapshot
        | where GeneratedAt < publicPreview
        | extend ViewedAt = GeneratedAt
        | project-away GeneratedAt;
    let getSnapshot =
        Aggregation
        | where Action == "GetSnapshotAPICalled"
        | join kind=inner genSnapshot on tenantId, reportName
        | where TIMESTAMP > GeneratedAt
        | summarize ViewedAt = min(TIMESTAMP) by tenantId, reportName
        | union backfillView;
    let ISVOnboard =
        getSnapshot
        | summarize OnboardedAt = min(ViewedAt) by tenantId;

    // Active ISVs vs Guests (Azure Portal extension)
    ExtTelemetry
    | where extension == "Microsoft_Azure_AppComplianceAutomation"
      and tenantId !in (cluster('mcatprodkusto.westus3.kusto.windows.net').database('GenevaDb').ACATTeamInternalTenantIds())
    | extend day = bin(TIMESTAMP, 1d)
    | summarize nISVs = dcount(tenantId),
                nActiveISVs = dcountif(tenantId, action endswith "Sent")
      by day
    | extend nGuests = nISVs - nActiveISVs

    // Offer configured (expanded)
    let createOffer =
        Aggregation | where Action == "CreateSucceeded" and isnotempty(offerGuid);
    let updateOffer =
        Aggregation | where Action == "UpdateSucceeded" and isnotempty(offerGuid);
    let offerConfigured =
        union updateOffer, createOffer
        | join kind=inner getSnapshot on tenantId, reportName
        | summarize ConfiguredofferGuidAt = min(TIMESTAMP) by tenantId, reportName, offerGuid
        | summarize arg_max(ConfiguredofferGuidAt, *) by tenantId, reportName
        | mv-expand offerGuid = split(offerGuid, ",")
        | project tenantId, reportName, offerGuid = trim(@"\s", tostring(offerGuid)), ConfiguredofferGuidAt;
    ```

- Join template (tenant/report grain)
  - Description: Safely align snapshot/view events per tenant/report with appropriate join kind and column hygiene.
  - Snippet:
    ```kusto
    let genSnapshot =
        Aggregation
        | where Action == "GenSnapshotSucceeded"
        | summarize GeneratedAt = min(TIMESTAMP) by tenantId, reportName;

    let getSnapshot =
        Aggregation
        | where Action == "GetSnapshotAPICalled"
        | join kind=inner genSnapshot on tenantId, reportName
        | where TIMESTAMP > GeneratedAt
        | summarize ViewedAt = min(TIMESTAMP) by tenantId, reportName;

    // Post-join hygiene example when enriching with Product360
    let tenantInfo =
        cluster('u360sec').database('KPIData').Product360CustomerSubscriptions
        | distinct Customer_TenantId, Customer_TenantName, Customer_TenantDisplayName;

    getSnapshot
    | join kind=leftouter tenantInfo on $left.tenantId == $right.Customer_TenantId
    | project-rename TenantName = Customer_TenantName, TenantDisplayName = Customer_TenantDisplayName
    | project-away Customer_TenantId
    ```

## Query Building Blocks (Copy-paste snippets, contains snippets and description)

- Time window template (with safe end time)
  - Description: Use this to scope queries and avoid partial current-day data.
  - Snippet:
    ```kusto
    // Time window with completeness-safe end
    let StartTime = ago(30d);
    let EffectiveEnd = startofday(now()); // exclude current (possibly incomplete) day
    T
    | where TIMESTAMP between (StartTime .. EffectiveEnd - 1ms)
    | summarize by bin(TIMESTAMP, 1d)
    ```

- Join template (tenant/report grain)
  - Description: Safely align snapshot/view events per tenant/report with appropriate join kind and column hygiene.
  - Snippet:
    ```kusto
    let genSnapshot =
        Aggregation
        | where Action == "GenSnapshotSucceeded"
        | summarize GeneratedAt = min(TIMESTAMP) by tenantId, reportName;

    let getSnapshot =
        Aggregation
        | where Action == "GetSnapshotAPICalled"
        | join kind=inner genSnapshot on tenantId, reportName
        | where TIMESTAMP > GeneratedAt
        | summarize ViewedAt = min(TIMESTAMP) by tenantId, reportName;

    // Post-join hygiene example when enriching with Product360
    let tenantInfo =
        cluster('u360sec').database('KPIData').Product360CustomerSubscriptions
        | distinct Customer_TenantId, Customer_TenantName, Customer_TenantDisplayName;

    getSnapshot
    | join kind=leftouter tenantInfo on $left.tenantId == $right.Customer_TenantId
    | project-rename TenantName = Customer_TenantName, TenantDisplayName = Customer_TenantDisplayName
    | project-away Customer_TenantId
    ```

- De-dup pattern
  - Description: Keep the latest (or earliest) row per entity, and cumulative counts for “ever” metrics.
  - Snippet:
    ```kusto
    // Latest event per tenant
    Aggregation
    | summarize arg_max(TIMESTAMP, *) by tenantId

    // Earliest event per tenant
    Aggregation
    | summarize arg_min(TIMESTAMP, *) by tenantId

    // Cumulative distinct tenants over time
    X
    | make-series n=dcount(tenantId) on TimeCol from bin(datetime(2022-12-10), 1d) to now() step 1d
    | mv-expand n, TimeCol
    | extend TimeCol = todatetime(TimeCol)
    | order by TimeCol asc
    | serialize Acc = row_cumsum(toint(n))
    | project-away n
    ```

- Important filters (internal/test removal; offer gating)
  - Description: Standard filters to remove internal tenants and enforce offer presence.
  - Snippet:
    ```kusto
    // Internal tenants (function or table)
    | where tenantId !in (cluster('mcatprodkusto.westus3.kusto.windows.net').database('GenevaDb').ACATTeamInternalTenantIds())

    // Offer presence
    | where isnotempty(offerGuid)

    // Deny specific tenantIds (explicit denylist)
    | where tenantId !in ("972de77a-552f-45ca-96ef-0b3d91110db4", "800398a7-3ef1-41fe-824a-687dc6e0b1d9", "...")
    ```

- Important definitions (Onboarding, Active/Guest, Offer configured)
  - Description: Reusable definitions to align metrics across queries.
  - Snippet:
    ```kusto
    // Onboarding: earliest view after snapshot (with backfill pre-publicPreview)
    let publicPreview = datetime(2022-12-13);
    let genSnapshot =
        Aggregation
        | where Action == "GenSnapshotSucceeded"
        | summarize GeneratedAt = min(TIMESTAMP) by tenantId, reportName;
    let backfillView =
        genSnapshot
        | where GeneratedAt < publicPreview
        | extend ViewedAt = GeneratedAt
        | project-away GeneratedAt;
    let getSnapshot =
        Aggregation
        | where Action == "GetSnapshotAPICalled"
        | join kind=inner genSnapshot on tenantId, reportName
        | where TIMESTAMP > GeneratedAt
        | summarize ViewedAt = min(TIMESTAMP) by tenantId, reportName
        | union backfillView;
    let ISVOnboard =
        getSnapshot
        | summarize OnboardedAt = min(ViewedAt) by tenantId;

    // Active ISVs vs Guests (Azure Portal extension)
    ExtTelemetry
    | where extension == "Microsoft_Azure_AppComplianceAutomation"
      and tenantId !in (cluster('mcatprodkusto.westus3.kusto.windows.net').database('GenevaDb').ACATTeamInternalTenantIds())
    | extend day = bin(TIMESTAMP, 1d)
    | summarize nISVs = dcount(tenantId),
                nActiveISVs = dcountif(tenantId, action endswith "Sent")
      by day
    | extend nGuests = nISVs - nActiveISVs

    // Offer configured (expanded)
    let createOffer =
        Aggregation | where Action == "CreateSucceeded" and isnotempty(offerGuid);
    let updateOffer =
        Aggregation | where Action == "UpdateSucceeded" and isnotempty(offerGuid);
    let offerConfigured =
        union updateOffer, createOffer
        | join kind=inner getSnapshot on tenantId, reportName
        | summarize ConfiguredofferGuidAt = min(TIMESTAMP) by tenantId, reportName, offerGuid
        | summarize arg_max(ConfiguredofferGuidAt, *) by tenantId, reportName
        | mv-expand offerGuid = split(offerGuid, ",")
        | project tenantId, reportName, offerGuid = trim(@"\s", tostring(offerGuid)), ConfiguredofferGuidAt;
    ```

- ID parsing/derivation
  - Description: Extract values from JSON fields and multi-value attributes, and normalize API endpoints.
  - Snippet:
    ```kusto
    // Extract reportName from dynamic payload
    ExtTelemetry
    | extend reportName = tostring(parse_json(data)["reportName"])

    // Collapse APIs to a common prefix
    HttpResponse
    | extend targetAPI = iff(targetUri startswith "/providers/Microsoft.AppComplianceAutomation/reports/",
                             "/providers/Microsoft.AppComplianceAutomation/reports/", targetUri),
             targetAPIandMethod = strcat(httpMethod, " ", targetAPI)
    ```

- Sharded union
  - Description: Merge same-schema sources across clusters/regions; normalize then summarize.
  - Snippet:
    ```kusto
    union
      cluster('mcatprodkusto.westus3.kusto.windows.net').database('GenevaDb').HttpResponse,
      cluster('<other-cluster>').database('<db>').HttpResponse
    | where TIMESTAMP between (ago(7d) .. now())
    | extend hour = bin(TIMESTAMP, 1h)
    | summarize count() by httpStatusCode, hour
    ```

## Example Queries (with explanations)

1) ISV funnel and cumulative trends with MoM
- Description: Builds a multi-stage funnel from snapshot generation to first view, offer configuration, and app compliance report request. Computes cumulative (ever) counts and a 30-day MoM rate. Enriches tenant metadata and excludes sample “Contoso” tenants. Adapt publicPreview date and filters as needed.
```kusto
let publicPreview = datetime("2022-12-10");
let tenantInfo =
    cluster('u360sec').database('KPIData').Product360CustomerSubscriptions
    | distinct Customer_TenantId, Customer_TenantName, Customer_TenantDisplayName;

let genSnapshot =
    Aggregation
    | where Action == 'GenSnapshotSucceeded'
    | join kind=leftouter tenantInfo on $left.tenantId == $right.Customer_TenantId
    | where Customer_TenantName !has "Contoso"
    | summarize GeneratedAt = min(TIMESTAMP) by tenantId, reportName;

let backfillView =
    genSnapshot
    | where GeneratedAt < datetime('2022-12-13')
    | extend ViewedAt = GeneratedAt
    | project-away GeneratedAt;

let acc_genSnapshot =
    genSnapshot
    | summarize GeneratedAt = min(GeneratedAt) by tenantId
    | make-series n = dcount(tenantId) on GeneratedAt from bin(publicPreview, 1d) to now() step 1d
    | mv-expand n, GeneratedAt
    | extend GeneratedAt = todatetime(GeneratedAt)
    | sort by GeneratedAt asc
    | serialize acc_GeneratedAt = row_cumsum(toint(n))
    | project-away n;

let getSnapshot =
    Aggregation
    | where Action == 'GetSnapshotAPICalled'
    | join kind=inner genSnapshot on tenantId, reportName
    | where TIMESTAMP > GeneratedAt
    | summarize ViewedAt = min(TIMESTAMP) by tenantId, reportName
    | union backfillView;

let acc_getSnapshot =
    getSnapshot
    | summarize ViewedAt = min(ViewedAt) by tenantId
    | make-series n = dcount(tenantId) on ViewedAt from bin(publicPreview, 1d) to now() step 1d
    | mv-expand n, ViewedAt
    | extend ViewedAt = todatetime(ViewedAt)
    | sort by ViewedAt asc
    | serialize acc_ViewedAt = row_cumsum(toint(n))
    | project-away n;

let createOfferGuid = Aggregation | where Action == 'CreateSucceeded' and isnotempty(offerGuid);
let updateOfferGuid = Aggregation | where Action == 'UpdateSucceeded' and isnotempty(offerGuid);

let offerGUID =
    union updateOfferGuid, createOfferGuid
    | join kind=inner getSnapshot on tenantId, reportName
    | summarize ConfiguredofferGuidAt = min(TIMESTAMP) by tenantId, reportName, offerGuid
    | summarize arg_max(ConfiguredofferGuidAt, *) by tenantId, reportName
    | mv-expand offerGuid = split(offerGuid, ',')
    | project tenantId, reportName, offerGuid = trim(@"\s", tostring(offerGuid)), ConfiguredofferGuidAt;

let acc_offerGuid =
    offerGUID
    | summarize FirstConfiguredat = arg_min(ConfiguredofferGuidAt, *) by tenantId
    | make-series n = dcount(tenantId) on FirstConfiguredat from bin(publicPreview, 1d) to now() step 1d
    | mv-expand n, FirstConfiguredat
    | extend FirstConfiguredat = todatetime(FirstConfiguredat)
    | sort by FirstConfiguredat asc
    | serialize acc_FirstConfiguredat = row_cumsum(toint(n))
    | project-away n;

let appCompliance =
    Aggregation
    | where Action == 'ReportDownloadedByAppCompliance'
    | join kind=leftouter offerGUID on $left.offerGuid == $right.offerGuid
    | where isnotempty(tenantId1) and TIMESTAMP > ConfiguredofferGuidAt
    | summarize ReportRequestedAt = min(TIMESTAMP) by tenantId1, reportName, offerGuid;

let acc_AppCompliance =
    appCompliance
    | summarize FirstRequestedAt = arg_min(ReportRequestedAt, *) by tenantId1
    | make-series n = dcount(tenantId1) on FirstRequestedAt from bin(publicPreview, 1d) to now() step 1d
    | mv-expand n, FirstRequestedAt
    | extend FirstRequestedAt = todatetime(FirstRequestedAt)
    | sort by FirstRequestedAt asc
    | serialize acc_FirstRequestedAt = row_cumsum(toint(n))
    | project-away n;

acc_genSnapshot
| join kind=leftouter acc_getSnapshot on $left.GeneratedAt == $right.ViewedAt
| join kind=leftouter acc_offerGuid on $left.ViewedAt == $right.FirstConfiguredat
| join kind=leftouter acc_AppCompliance on $left.FirstConfiguredat == $right.FirstRequestedAt
| serialize acc_ViewedAt
| extend MoM = todouble(acc_ViewedAt - prev(acc_ViewedAt, 30)) / prev(acc_ViewedAt, 30) * 100
| extend MoM = iff(isnull(MoM), 0.0, MoM)
| sort by GeneratedAt desc
```

2) API call volume by status, API, and hour (7d)
- Description: Groups HttpResponse events hourly by canonicalized API prefix and method, excluding internal tenants. Change timeframe or filtering as needed. Fully qualify ACATTeamInternalTenantIds if required in your environment.
```kusto
HttpResponse
| where TIMESTAMP > ago(7d)
  and tenantId !in (ACATTeamInternalTenantIds)
| extend targetAPI = iff(targetUri startswith "/providers/Microsoft.AppComplianceAutomation/reports/",
                         "/providers/Microsoft.AppComplianceAutomation/reports/", targetUri),
         hour = bin(TIMESTAMP, 1h),
         targetAPIandMethod = strcat(httpMethod, " ", targetAPI)
| summarize count() by targetAPIandMethod, hour, httpStatusCode
```

3) Azure Portal extension usage: Active ISVs vs Guests per day
- Description: Uses ExtTelemetry from Azure Portal to count daily ISVs and active ISVs (action endswith "Sent"), then derives guests. Excludes internal tenants via cross-cluster function.
```kusto
let tenantInfo =
    cluster('u360sec').database('KPIData').Product360CustomerSubscriptions
    | distinct Customer_TenantId, Customer_TenantName, Customer_TenantDisplayName;

ExtTelemetry
| where extension == "Microsoft_Azure_AppComplianceAutomation"
  and tenantId !in (cluster('mcatprodkusto.westus3.kusto.windows.net').database('GenevaDb').ACATTeamInternalTenantIds())
| extend reportName = tostring(parse_json(data)["reportName"]),
         day = bin(TIMESTAMP, 1d)
| summarize nISVs = dcount(tenantId),
            nActiveISVs = dcountif(tenantId, action endswith "Sent")
  by day
| extend nGuests = nISVs - nActiveISVs
```

4) Error volume by type and hour (14d)
- Description: Counts errors by errorType and hour over the last 14 days using PreciseTimeStamp for time filter and TIMESTAMP for binning and min timestamp. Adjust the window as needed.
```kusto
Error
| where PreciseTimeStamp >= now(-14d)
| extend hourlyTime = bin(TIMESTAMP, 1h)
| summarize count(), TimeStamp = min(TIMESTAMP) by errorType, hourlyTime
```

5) ISV retention/cohort curve from onboarding to last activity
- Description: Builds cohorts by OnboardedAt (30-day bins) and tracks how many ISVs remain active by lastActiveAt windows; computes an accumulated count across bins. Excludes a denylist of tenants and uses publicPreview anchor to align bins.
```kusto
let publicPreview = datetime('2022-12-13');

let genSnapshot =
    Aggregation
    | where Action == 'GenSnapshotSucceeded'
    | where tenantId !in ("972de77a-552f-45ca-96ef-0b3d91110db4", "800398a7-3ef1-41fe-824a-687dc6e0b1d9",
                          "49511fb1-4af8-4eb3-a4f3-0a1b3038b64d", "46fbc19c-18f2-4c28-b879-c08e01afd40f",
                          "6a1c431e-7372-45c4-a780-555e7ae1a2ac", "217e0081-c272-40b1-921c-94745eba0eed",
                          "b16461d0-d7eb-46c1-b3c1-86f2a55c9042", "e947416c-06b4-4fa6-9889-aeea22e44139",
                          "ef05883f-b8b3-4031-8ffc-1dc84f621dff", "bbdddcf8-f6b5-4d8b-aa8b-8db0c66d0c6a",
                          "f70e581e-768a-4fd4-b088-7540530f8377", "b2c0b6ec-0036-4fe9-b222-f419713a4772",
                          "06f05128-8a81-4bc7-95e8-81e3de737730", "b80aed20-39d5-494e-aa1d-15ad0a398251",
                          "e6fb4586-2f1f-45af-9af8-a5a101a6c3de", "a8667cb7-9598-42ad-b1af-37fa62890999",
                          "f765057c-99a1-48ca-8149-00c006fba601")
    | summarize GeneratedAt = min(TIMESTAMP) by tenantId, reportName;

let backfillView =
    genSnapshot
    | where GeneratedAt < publicPreview
    | extend ViewedAt = GeneratedAt
    | project-away GeneratedAt;

let ISVonboard =
    Aggregation
    | where Action == 'GetSnapshotAPICalled'
    | join kind=inner genSnapshot on tenantId, reportName
    | where TIMESTAMP > GeneratedAt
    | summarize ViewedAt = min(TIMESTAMP) by tenantId, reportName
    | union backfillView
    | summarize OnboardedAt = min(ViewedAt) by tenantId;

Aggregation
| where Action != "GenSnapshotSucceeded" or TIMESTAMP <= publicPreview
| summarize arg_max(TIMESTAMP, *) by tenantId
| extend lastActiveAt = TIMESTAMP
| join kind=inner ISVonboard on tenantId
| make-series nISVs = count() on bin_at(lastActiveAt, 30d, publicPreview)
                      from publicPreview - 30d
                      to bin_at(now() + 30d, 30d, publicPreview) step 30d
                      by bin_at(OnboardedAt, 30d, publicPreview)
| mv-expand nISVs, lastActiveAt
| extend lastActiveAt = todatetime(lastActiveAt), nISVs = toint(nISVs)
| where lastActiveAt >= OnboardedAt
| extend Nago = toint(format_timespan(lastActiveAt - OnboardedAt, 'd'))
| sort by OnboardedAt, lastActiveAt
| serialize acc = row_cumsum(nISVs, OnboardedAt != prev(OnboardedAt))
```

6) Offer GUID configuration expansion (from the funnel)
- Description: Identifies first configuration time per tenant/report, expands multiple GUIDs, and trims whitespace. Use this to link offers to later compliance events.
```kusto
let genSnapshot =
    Aggregation
    | where Action == 'GenSnapshotSucceeded'
    | summarize GeneratedAt = min(TIMESTAMP) by tenantId, reportName;

let backfillView =
    genSnapshot
    | where GeneratedAt < datetime('2022-12-13')
    | extend ViewedAt = GeneratedAt
    | project-away GeneratedAt;

let getSnapshot =
    Aggregation
    | where Action == 'GetSnapshotAPICalled'
    | join kind=inner genSnapshot on tenantId, reportName
    | where TIMESTAMP > GeneratedAt
    | summarize ViewedAt = min(TIMESTAMP) by tenantId, reportName
    | union backfillView;

let createOfferGuid = Aggregation | where Action == 'CreateSucceeded' and isnotempty(offerGuid);
let updateOfferGuid = Aggregation | where Action == 'UpdateSucceeded' and isnotempty(offerGuid);

union updateOfferGuid, createOfferGuid
| join kind=inner getSnapshot on tenantId, reportName
| summarize ConfiguredofferGuidAt = min(TIMESTAMP) by tenantId, reportName, offerGuid
| summarize arg_max(ConfiguredofferGuidAt, *) by tenantId, reportName
| mv-expand offerGuid = split(offerGuid, ',')
| project tenantId, reportName, offerGuid = trim(@"\s", tostring(offerGuid)), ConfiguredofferGuidAt
```

7) Earliest report view per tenant/report with backfill
- Description: Pivots the earliest “GetSnapshotAPICalled” after snapshot generation into a “viewed at” definition, with backfill to snapshot time for pre-publicPreview reports.
```kusto
let publicPreview = datetime('2022-12-13');

let genSnapshot =
    Aggregation
    | where Action == 'GenSnapshotSucceeded'
    | summarize GeneratedAt = min(TIMESTAMP) by tenantId, reportName;

let backfillView =
    genSnapshot
    | where GeneratedAt < publicPreview
    | extend ViewedAt = GeneratedAt
    | project-away GeneratedAt;

let getSnapshot =
    Aggregation
    | where Action == 'GetSnapshotAPICalled'
    | join kind=inner genSnapshot on tenantId, reportName
    | where TIMESTAMP > GeneratedAt
    | summarize ViewedAt = min(TIMESTAMP) by tenantId, reportName
    | union backfillView;

getSnapshot
```

## Reasoning Notes (only if uncertain)
- ACATTeamInternalTenantIds appears as both a bare name and cluster-qualified function; we assume it is available as a function/table in GenevaDb and may have a local alias in some contexts.
- The Aggregation database seems to contain a table also named Aggregation; we adopt that usage based on queries directly referencing Aggregation.
- Timezone is unspecified; we assume UTC, which matches Kusto default; if a product-specific timezone exists, adjust bins and day boundaries accordingly.
- now(-14d) is used to filter 14 days back; ago(14d) is equivalent and more idiomatic; we retained semantics but recommend ago() for clarity.
- Public preview anchor dates (2022-12-10 and 2022-12-13) appear in different queries; we treat them as scenario-specific anchors rather than a single canonical date.
- Product360CustomerSubscriptions is used for tenant enrichment (names/display); keys inferred from join suggest Customer_TenantId aligns with tenantId; we keep joins leftouter to avoid dropping telemetry-only tenants.
- HttpResponse and Error tables likely reside in mcatprodkusto.westus3 (GenevaDb) per references; in environments where the default database context differs, fully qualify to avoid ambiguity.
- “Active ISV” defined as action endswith "Sent" is specific to ExtTelemetry records for the Portal extension and may not generalize to other channels.
- Offer GUID splitting assumes a comma-delimited string; for other delimiters or edge cases, adjust split() accordingly.

## Canonical Tables

Below are the canonical tables used by ACAT queries, ordered by priority. Each section explains what the table represents, typical usage patterns, common filters, and key columns inferred from actual queries. Where cross-cluster sources are used, the cluster and database are noted.

### Table name: Aggregation (cluster acattelemetry.eastus.kusto.windows.net / database Aggregation)
- Priority: Normal
- What this table represents:
  - Fact/event telemetry for ACAT features with per-event TIMESTAMP.
  - Actions observed include GenSnapshotSucceeded, GetSnapshotAPICalled, CreateSucceeded, UpdateSucceeded, ReportDownloadedByAppCompliance.
  - Zero rows for a tenant within a time window typically imply no activity captured for those actions in that period.
- Freshness expectations:
  - Unknown. Treat current-day data cautiously; prefer time windows that end at least several hours in the past when building dashboards.
- When to use:
  - Track snapshot generation (first GenSnapshotSucceeded per tenant/report).
  - Identify when snapshots are first viewed via GetSnapshotAPICalled after generation.
  - Measure when offers are first configured (CreateSucceeded/UpdateSucceeded with non-empty offerGuid).
  - Detect report downloads by AppCompliance and sequence adoption funnels over time.
- When to avoid:
  - Do not assume offerGuid is singular; queries show it can contain comma-separated values and must be split.
  - Avoid mixing HTTP-level traffic analysis here; use HttpResponse for endpoint-level metrics.
  - Don’t treat absence of actions as definitive inactivity without validating tenant filtering (e.g., internal tenants exclusion).
- Similar tables & how to choose:
  - HttpResponse: choose for HTTP volume/status analyses; Aggregation is feature-action telemetry.
  - ExtTelemetry: use for Azure Portal extension usage; Aggregation is service-side telemetry.
  - Error: use for error categorization; Aggregation focuses on actions.
- Common Filters:
  - Action in a defined set (GenSnapshotSucceeded, GetSnapshotAPICalled, CreateSucceeded, UpdateSucceeded, ReportDownloadedByAppCompliance).
  - TIMESTAMP time windows (daily binning via 1d; hourly binning uncommon here).
  - Exclude internal/test tenants by list or function (e.g., ACATTeamInternalTenantIds or explicit tenantId lists).
- Table columns:
  | Column           | Type     | Description or meaning                                                                 |
  |------------------|----------|-----------------------------------------------------------------------------------------|
  | PreciseTimeStamp | datetime | High-precision event time; can be used for tight windowing and ordering                |
  | TIMESTAMP        | datetime | Event occurrence time commonly used for binning and “first event per tenant/report”    |
  | reportName       | string   | Report identifier/name referenced across actions                                       |
  | offerGuid        | string   | Offer identifier; can contain multiple GUIDs separated by commas (split before use)    |
  | tenantId         | string   | Tenant identifier used for grouping/exclusion                                          |
  | Action           | string   | Event/action type (e.g., GenSnapshotSucceeded, GetSnapshotAPICalled, etc.)             |
- Column Explain:
  - TIMESTAMP: primary time for summarization (min/max), binning (1d), and ordering.
  - Action: core filter to select scenario-specific subsets (snapshot generation, view, create/update, download).
  - tenantId: used for distinct counts, joins, and internal-tenant exclusion.
  - reportName: join key to connect generation/view/configuration sequences.
  - offerGuid: split by comma and trim before per-offer analytics; used in downstream joins (e.g., AppCompliance downloads).

Example schema query (for reference):
```kusto
cluster('acattelemetry.eastus.kusto.windows.net').database('Aggregation').Aggregation
| getschema
```

---

### Table name: Product360CustomerSubscriptions (cluster u360sec / database KPIData)
- Priority: Normal
- What this table represents:
  - Customer subscription metadata, used to map tenant IDs to names and display names.
  - Acts as a snapshot-like dimension table for enriching telemetry with customer names.
- Freshness expectations:
  - Unknown. Treat as metadata that may lag operational telemetry; avoid using it to infer current activity.
- When to use:
  - Join to add Customer_TenantName and Customer_TenantDisplayName to telemetry.
  - Filter out known demo tenants (e.g., Customer_TenantName not containing “Contoso”).
  - Produce distinct tenant lists for enrichment.
- When to avoid:
  - Do not use it as the source of truth for active usage or time series counts.
  - Avoid relying on it for time-based filters (no TIMESTAMP used in queries).
- Similar tables & how to choose:
  - None observed; this is the primary metadata source used for tenant naming.
- Common Filters:
  - distinct Customer_TenantId, Customer_TenantName, Customer_TenantDisplayName.
  - Filter by Customer_TenantName content (e.g., exclude “Contoso”).
- Table columns:
  | Column                     | Type   | Description or meaning                           |
  |----------------------------|--------|--------------------------------------------------|
  | Customer_TenantId          | string | Tenant identifier for joining to telemetry       |
  | Customer_TenantName        | string | Customer tenant canonical name                   |
  | Customer_TenantDisplayName | string | Customer tenant display name for UI/reporting    |
- Column Explain:
  - Customer_TenantId: join key to telemetry tables by tenantId.
  - Customer_TenantName: used for filtering out demo tenants.
  - Customer_TenantDisplayName: presentation-friendly name for dashboards and reports.

---

### Table name: HttpResponse (cluster mcatprodkusto.westus3.kusto.windows.net / database unknown)
- Priority: Normal
- What this table represents:
  - HTTP-level telemetry (requests/responses) for ACAT endpoints.
  - Used to aggregate counts by endpoint, method, status code, and hour.
- Freshness expectations:
  - Unknown. When monitoring live trends, use short windows and hourly bins.
- When to use:
  - Measure API traffic volume and status distribution by endpoint and method.
  - Track hourly trends (bin TIMESTAMP by 1h).
  - Normalize endpoints to focus on report APIs (e.g., collapse to '/providers/Microsoft.AppComplianceAutomation/reports/').
- When to avoid:
  - Avoid mixing internal tenants; always exclude ACATTeamInternalTenantIds to reduce noise.
  - Don’t use for feature-action sequences (use Aggregation instead).
- Similar tables & how to choose:
  - Aggregation: service-side events; HttpResponse for HTTP request/response metrics.
  - Error: for error categorization rather than per-endpoint volume.
- Common Filters:
  - TIMESTAMP > ago(7d).
  - tenantId !in (ACATTeamInternalTenantIds).
  - extend targetAPI and targetAPIandMethod; summarize count() by targetAPIandMethod, hour, httpStatusCode.
- Table columns:
  | Column         | Type     | Description or meaning                                           |
  |----------------|----------|------------------------------------------------------------------|
  | TIMESTAMP      | datetime | Request/response time; binned hourly for time series             |
  | tenantId       | string   | Tenant identifier; exclude internal tenants                      |
  | targetUri      | string   | Request target URI; normalized to report APIs in queries         |
  | httpMethod     | string   | HTTP method (GET/POST/etc.); combined with endpoint in summaries |
  | httpStatusCode | int      | HTTP status code for response                                    |
- Column Explain:
  - TIMESTAMP: bin to 1h for hourly trend charts.
  - tenantId: always apply internal-tenant exclusion.
  - targetUri/httpMethod: combine to analyze per-endpoint-method traffic.
  - httpStatusCode: categorize responses (success/failure) in summaries.

---

### Table name: ACATTeamInternalTenantIds (cluster mcatprodkusto.westus3.kusto.windows.net / database GenevaDb)
- Priority: Normal
- What this table represents:
  - A list (or function output) of internal/test tenant IDs used for filtering.
  - Queries reference both the table and a function form ACATTeamInternalTenantIds().
- Freshness expectations:
  - Unknown. Treat as a static/external exclusion list that may change infrequently.
- When to use:
  - Exclude internal/test tenants from usage, traffic, and retention analyses.
  - Apply via “tenantId !in (ACATTeamInternalTenantIds)” or function form from GenevaDb.
- When to avoid:
  - Avoid using it as an inclusion list; it is specifically for exclusion.
- Similar tables & how to choose:
  - Explicit tenant ID exclusion lists: prefer ACATTeamInternalTenantIds for maintainability.
- Common Filters:
  - tenantId !in (ACATTeamInternalTenantIds) or !in (cluster('...').database('GenevaDb').ACATTeamInternalTenantIds()).
- Table columns:
  | Column   | Type   | Description or meaning                      |
  |----------|--------|---------------------------------------------|
  | tenantId | string | Internal/test tenant ID for exclusion logic |
- Column Explain:
  - tenantId: used directly in “!in” filters across HTTP, telemetry, and adoption queries.

---

### Table name: ExtTelemetry (cluster azportalpartnerrow.westus.kusto.windows.net / database unknown)
- Priority: Normal
- What this table represents:
  - Azure Portal extension telemetry; filtered to extension == "Microsoft_Azure_AppComplianceAutomation".
  - Used to measure ISV activity (active vs. guests) and daily counts.
- Freshness expectations:
  - Unknown. For daily trends, bin TIMESTAMP to 1d and avoid same-day partials when building charts.
- When to use:
  - Count ISVs and active ISVs per day (distinct tenantId; action endswith 'Sent').
  - Derive guest counts as nISVs - nActiveISVs.
  - Filter to the specific portal extension string.
- When to avoid:
  - Don’t include other portal extensions; always filter by extension string.
  - Exclude internal tenants via ACATTeamInternalTenantIds() from GenevaDb to avoid skew.
- Similar tables & how to choose:
  - Aggregation: service-side events; ExtTelemetry: portal-side extension usage.
- Common Filters:
  - extension == "Microsoft_Azure_AppComplianceAutomation".
  - tenantId !in (cluster('mcatprodkusto.westus3.kusto.windows.net').database('GenevaDb').ACATTeamInternalTenantIds()).
  - day = bin(TIMESTAMP, 1d); summarize by day.
  - action endswith "Sent" to define “active”.
- Table columns:
  | Column     | Type     | Description or meaning                                                |
  |------------|----------|------------------------------------------------------------------------|
  | TIMESTAMP  | datetime | Event time; binned to 1d for daily activity                           |
  | extension  | string   | Portal extension name; filter to Microsoft_Azure_AppComplianceAutomation |
  | tenantId   | string   | ISV tenant identifier                                                  |
  | data       | dynamic  | JSON payload; queries parse reportName from this field                 |
  | action     | string   | Action label; “endswith 'Sent'” indicates active interactions         |
- Column Explain:
  - extension: must equal the ACAT extension to scope analyses.
  - tenantId: distinct counts for ISVs and active ISVs.
  - action: classify active vs. guests (active if endswith 'Sent').
  - data: parse to extract fields like reportName when needed.
  - TIMESTAMP: bin to 1d for daily trend summaries.

---

### Table name: Error (cluster mcatprodkusto.westus3.kusto.windows.net / database unknown)
- Priority: Normal
- What this table represents:
  - Error telemetry with categorical errorType and event time.
  - Used to trend error counts hourly over recent periods.
- Freshness expectations:
  - Unknown. Queries commonly look back 14 days; consider a rolling window for monitors.
- When to use:
  - Summarize count() by errorType and hourly time buckets.
  - Track minimum TIMESTAMP per bucket for context.
- When to avoid:
  - For endpoint-level status distributions use HttpResponse; Error is for error categorization.
- Similar tables & how to choose:
  - HttpResponse: traffic/status codes; Error: error types.
- Common Filters:
  - PreciseTimeStamp >= now(-14d).
  - hourlyTime = bin(TIMESTAMP, 1h); summarize count() by errorType, hourlyTime.
- Table columns:
  | Column           | Type     | Description or meaning                                          |
  |------------------|----------|------------------------------------------------------------------|
  | PreciseTimeStamp | datetime | High-precision event time; used for lookback window filtering   |
  | TIMESTAMP        | datetime | Event time; binned to 1h for hourly error trends                 |
  | errorType        | string   | Error category/type used in summarizations                       |
- Column Explain:
  - errorType: primary grouping for error analyses.
  - PreciseTimeStamp: filter start for lookback windows (e.g., 14 days).
  - TIMESTAMP: bin to hourly buckets for trend charts.

---

Notes and patterns observed across queries:
- Time binning conventions:
  - Hourly: bin(TIMESTAMP, 1h) for HttpResponse and Error.
  - Daily: bin(TIMESTAMP, 1d) for ExtTelemetry and adoption funnels.
- Tenant filtering:
  - Always exclude internal/test tenants using ACATTeamInternalTenantIds (table or function).
  - Some analyses additionally exclude explicit tenantId lists (e.g., in retention-type queries).
- Adoption sequencing & accumulations:
  - Use min(TIMESTAMP) per tenant/report to capture “first occurrence” milestones.
  - Row-level accumulations via row_cumsum and make-series for cumulative trend lines.
  - Offer GUID handling:
  - offerGuid can be comma-separated; split and trim before per-offer analytics.
- Freshness:
  - No explicit refresh SLAs provided; prefer conservative windows and avoid same-day partials for dashboards.