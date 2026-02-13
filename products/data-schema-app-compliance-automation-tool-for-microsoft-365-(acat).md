# App Compliance Automation Tool for Microsoft 365 (ACAT) - Product and Data Overview Template

## 1. Product Overview

App Compliance Automation Tool for Microsoft 365 (ACAT) is a service that helps Independent Software Vendors (ISVs) automate compliance assessments and reporting for Microsoft 365 applications. This draft overview establishes the initial schema so PMAgent can interpret ACAT-specific telemetry and queries. Please refine this section with product-specific business context and goals as needed.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**:
App Compliance Automation Tool for Microsoft 365 (ACAT)
- **Product Nick Names**: 
**[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations.
- **Kusto Cluster**:
mcatprodkusto.westus3.kusto.windows.net
- **Kusto Database**:
GenevaDb
- **Access Control**:
**[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed **groups/users** here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

# App Compliance Automation Tool for Microsoft 365 (ACAT) - Kusto Query Playbook

## Overview
ACAT onboarding-related Kusto queries and telemetry instructions covering ISV Trend, HTTP Response, Snapshot failure, Compliance Report, Active ISV and Guest, Error count, Azure Portal Usage, and ISV Retention. Author: JialinXin.

- Primary cluster: mcatprodkusto.westus3.kusto.windows.net
- Primary database: GenevaDb
- Also referenced:
  - acattelemetry.eastus.kusto.windows.net (Aggregation)
  - azportalpartnerrow.westus.kusto.windows.net (ExtTelemetry)
  - cluster('u360sec').database('KPIData') (Product360CustomerSubscriptions dimension)

## Conventions & Assumptions

### Time semantics
- Observed timestamp columns:
  - TIMESTAMP (canonical across HttpResponse, Aggregation, ExtTelemetry, Error)
  - PreciseTimeStamp (Error filters)
- Canonical Time Column: TIMESTAMP
  - Alignment pattern:
    ```kusto
    // Normalize to a canonical time column when mixing sources
    | project-rename Time = TIMESTAMP
    // If needed:
    // | extend Time = coalesce(TIMESTAMP, PreciseTimeStamp)
    ```
- Typical windows and bins:
  - Time windows: ago(7d), now(-14d), fixed datetimes (e.g., datetime('2022-12-10'))
  - Bins: 1h, 1d, 30d; anchored bins via bin_at(..., 30d, <anchor>)
  - Time-series accumulation via make-series → mv-expand → row_cumsum
- Timezone: Not specified. Assume UTC by default.

### Freshness & Completeness Gates
- Ingestion cadence and current-day completeness are not specified.
- Recommended practices:
  - Use an effective end time of startofday(ago(1d)) for daily analytics.
  - Add a multi-slice completeness gate (choose a sentinel like HttpResponse across key slices such as tenantId or region):
    ```kusto
    // Gate: last fully complete day with ≥ <MinSlices> tenants reporting within the day
    let MinSlices = 100;
    let CandidateDays =
        HttpResponse
        | summarize slices=dcount(tenantId) by day=startofday(TIMESTAMP)
        | where slices >= MinSlices
        | sort by day desc;
    let EffectiveEnd = toscalar(CandidateDays | top 1 by day | project day);
    // Use EffectiveEnd (exclusive) as the analysis end
    ```

### Joins & Alignment
- Frequent keys:
  - tenantId (core entity)
  - reportName (per-tenant report context)
  - offerGuid (can be CSV; split and normalize)
- Join kinds:
  - inner, leftouter
- Post-join hygiene:
  - Align keys with project-rename or extend
  - Drop helper columns with project-away
  - Resolve ambiguous columns with arg_min/arg_max patterns

### Filters & Idioms
- Default cohort exclusions:
  - Exclude internal/test tenants: tenantId !in (ACATTeamInternalTenantIds) or cross-cluster call to ACATTeamInternalTenantIds()
  - Exclude “Contoso” tenants in ISV trend: Customer_TenantName !has "Contoso"
  - Explicit tenantId exclusion lists for special analyses (e.g., retention)
- Action-based filters (Aggregation):
  - 'GenSnapshotSucceeded', 'GetSnapshotAPICalled', 'CreateSucceeded', 'UpdateSucceeded', 'ReportDownloadedByAppCompliance'
- ExtTelemetry filtering:
  - extension == "Microsoft_Azure_AppComplianceAutomation"
  - Active proxy: action endswith "Sent"
- HTTP routing/grouping:
  - targetUri startswith '/providers/Microsoft.AppComplianceAutomation/reports/' and canonicalization via iff + strcat
- Parsing/normalization:
  - parse_json, split CSV, trim(@"\s", ...)

### Cross-cluster/DB & Sharding
- Qualify sources explicitly when reading from other clusters/databases:
  ```kusto
  cluster('u360sec').database('KPIData').Product360CustomerSubscriptions
  cluster('mcatprodkusto.westus3.kusto.windows.net').database('GenevaDb').ACATTeamInternalTenantIds()
  ```
- Same-schema merging (if needed):
  - union sources → normalize time/keys → summarize
  - Order matters: normalize before summarize for correctness

### Table classes
- Fact/Event:
  - Aggregation (actioned events: GenSnapshotSucceeded, GetSnapshotAPICalled, Create/UpdateSucceeded, ReportDownloadedByAppCompliance)
  - HttpResponse (API calls)
  - Error (error events; PreciseTimeStamp present)
  - ExtTelemetry (portal extension telemetry; includes JSON field data)
- Dimension/Cohort:
  - Product360CustomerSubscriptions (tenant info: Customer_TenantId, names)
  - ACATTeamInternalTenantIds / ACATTeamInternalTenantIds() (internal/test cohort)

## Entity & Counting Rules (Core Definitions)

- Entity model:
  - Tenant (tenantId or Customer_TenantId)
  - Report (reportName) within a tenant
  - Offer (offerGuid), possibly multiple per report; can be CSV and must be split/trimmed
- Counting rules:
  - Use dcount(tenantId) or dcountif(...) for distinct counts
  - First/last event via arg_min/arg_max by keys
  - Accumulated counts with make-series + row_cumsum, after converting series to rows via mv-expand
- Business definitions (seen in queries):
  - Onboarded tenant (ISVonboard): min(ViewedAt), where ViewedAt is the earliest GetSnapshotAPICalled strictly after GenSnapshotSucceeded; includes backfill for pre-public preview
  - Active ISV: ExtTelemetry where action endswith "Sent"
  - Guests: ISVs - Active ISVs (by day)
  - Configured offer: earliest ConfiguredofferGuidAt derived from Aggregation CreateSucceeded/UpdateSucceeded joined to viewed snapshot

## Views (Reusable Layers)

- Public preview anchor (copied from Important definitions):
  ```kusto
  let PublicPreview = datetime('2022-12-13'); // set per analysis
  ```

- OnboardedAt (first view after generation, plus backfill) (copied from Important definitions):
  ```kusto
  let GenSnapshot =
      Aggregation
      | where Action == 'GenSnapshotSucceeded'
      | summarize GeneratedAt=min(TIMESTAMP) by tenantId, reportName;

  let BackfillView =
      GenSnapshot
      | where GeneratedAt < PublicPreview
      | extend ViewedAt = GeneratedAt
      | project tenantId, reportName, ViewedAt;

  let FirstViewAfterGen =
      Aggregation
      | where Action == 'GetSnapshotAPICalled'
      | join kind=inner GenSnapshot on (tenantId, reportName)
      | where TIMESTAMP > GeneratedAt
      | summarize ViewedAt=min(TIMESTAMP) by tenantId, reportName;

  let ISVonboard =
      union FirstViewAfterGen, BackfillView
      | summarize OnboardedAt=min(ViewedAt) by tenantId;
  ```

- Sharded/merged unions for offer configuration (copied from Sharded/merged unions):
  ```kusto
  let CreateOffer = Aggregation | where Action == 'CreateSucceeded' and isnotempty(offerGuid);
  let UpdateOffer = Aggregation | where Action == 'UpdateSucceeded' and isnotempty(offerGuid);
  union UpdateOffer, CreateOffer
  | summarize FirstConfiguredAt=min(TIMESTAMP) by tenantId, reportName, offerGuid
  ```

- ID parsing/derivation helpers (copied from ID parsing/derivation):
  ```kusto
  // Parse reportName from JSON payload:
  | extend reportName = tostring(parse_json(data)["reportName"])

  // offerGuid splitting and trimming:
  | mv-expand offerGuid = split(offerGuid, ',')
  | extend offerGuid = trim(@"\s", tostring(offerGuid))
  ```

## Query Building Blocks (Copy-paste snippets, contains snippets and description)

- Time window template
  - Description: Use consistent time windowing; avoid partial current day by using an effective end time.
  - Snippet:
    ```kusto
    let StartTime = ago(7d);
    let EffectiveEnd = startofday(ago(1d)); // avoid current day partials
    <FactTable>
    | where TIMESTAMP between (StartTime .. EffectiveEnd)
    | summarize ...
    ```

- Join template (tenant + report context)
  - Description: Align tenant and report keys; choose join kind based on inclusion policy.
  - Snippet:
    ```kusto
    let Left =
        Aggregation
        | where Action == 'GetSnapshotAPICalled'
        | project tenantId, reportName, LeftTime = TIMESTAMP;
    let Right =
        Aggregation
        | where Action == 'GenSnapshotSucceeded'
        | project tenantId, reportName, RightTime = TIMESTAMP;
    Left
    | join kind=inner Right on (tenantId, reportName)
    | where LeftTime > RightTime
    | project-away RightTime
    ```

- De-duplication patterns
  - Latest by key(s):
    ```kusto
    <Table>
    | summarize arg_max(TIMESTAMP, *) by tenantId
    ```
  - First by key(s):
    ```kusto
    <Table>
    | summarize arg_min(TIMESTAMP, *) by tenantId
    ```
  - Accumulated distinct tenants over time:
    ```kusto
    <Table>
    | summarize FirstAt=min(TIMESTAMP) by tenantId
    | make-series n=dcount(tenantId) on FirstAt from ago(30d) to now() step 1d
    | mv-expand n, FirstAt
    | extend FirstAt=todatetime(FirstAt)
    | serialize Acc=row_cumsum(toint(n))
    ```

- Important filters
  - Exclude internal tenants:
    ```kusto
    | where tenantId !in (ACATTeamInternalTenantIds)
    // or cross-cluster:
    // | where tenantId !in (cluster('mcatprodkusto.westus3.kusto.windows.net').database('GenevaDb').ACATTeamInternalTenantIds())
    ```
  - Exclude example tenants:
    ```kusto
    | where Customer_TenantName !has "Contoso"
    ```
  - Action gating:
    ```kusto
    | where Action in ('GenSnapshotSucceeded','GetSnapshotAPICalled','CreateSucceeded','UpdateSucceeded','ReportDownloadedByAppCompliance')
    ```
  - HTTP API normalization:
    ```kusto
    | extend targetAPI=iff(targetUri startswith '/providers/Microsoft.AppComplianceAutomation/reports/',
                           '/providers/Microsoft.AppComplianceAutomation/reports/', targetUri)
    | extend targetAPIandMethod=strcat(httpMethod, ' ', targetAPI)
    ```

- Important definitions
  - Public preview anchor:
    ```kusto
    let PublicPreview = datetime('2022-12-13'); // set per analysis
    ```
  - OnboardedAt (first view after generation, plus backfill):
    ```kusto
    let GenSnapshot =
        Aggregation
        | where Action == 'GenSnapshotSucceeded'
        | summarize GeneratedAt=min(TIMESTAMP) by tenantId, reportName;

    let BackfillView =
        GenSnapshot
        | where GeneratedAt < PublicPreview
        | extend ViewedAt = GeneratedAt
        | project tenantId, reportName, ViewedAt;

    let FirstViewAfterGen =
        Aggregation
        | where Action == 'GetSnapshotAPICalled'
        | join kind=inner GenSnapshot on (tenantId, reportName)
        | where TIMESTAMP > GeneratedAt
        | summarize ViewedAt=min(TIMESTAMP) by tenantId, reportName;

    let ISVonboard =
        union FirstViewAfterGen, BackfillView
        | summarize OnboardedAt=min(ViewedAt) by tenantId;
    ```

- ID parsing/derivation
  - Parse reportName from JSON payload:
    ```kusto
    | extend reportName = tostring(parse_json(data)["reportName"])
    ```
  - offerGuid splitting and trimming:
    ```kusto
    | mv-expand offerGuid = split(offerGuid, ',')
    | extend offerGuid = trim(@"\s", tostring(offerGuid))
    ```

- Sharded/merged unions
  - Merge same-schema event sources or variants:
    ```kusto
    let CreateOffer = Aggregation | where Action == 'CreateSucceeded' and isnotempty(offerGuid);
    let UpdateOffer = Aggregation | where Action == 'UpdateSucceeded' and isnotempty(offerGuid);
    union UpdateOffer, CreateOffer
    | summarize FirstConfiguredAt=min(TIMESTAMP) by tenantId, reportName, offerGuid
    ```

## Example Queries (with explanations)

1) ISV Trend
- Description: Computes accumulated counts across the ISV journey: first snapshot generation, first view (GetSnapshotAPICalled), first offerGuid configuration, and first App Compliance report download. It excludes “Contoso” tenants, anchors time series at public preview, and uses make-series + row_cumsum to produce cumulative curves and a MoM change. Adapt by changing the publicPreview date, filters (e.g., exclude different cohorts), or bin size.
```kusto
let publicPreview = datetime('2022-12-10');
let tenantInfo = cluster('u360sec').database('KPIData').Product360CustomerSubscriptions
| distinct Customer_TenantId, Customer_TenantName, Customer_TenantDisplayName;
let genSnapshot = Aggregation
| where Action == 'GenSnapshotSucceeded'
| join kind=leftouter tenantInfo on $left.tenantId == $right.Customer_TenantId
| where Customer_TenantName !has "Contoso"
| summarize GeneratedAt = min(TIMESTAMP) by tenantId, reportName;
let backfillView = genSnapshot
| where GeneratedAt < datetime('2022-12-13')
| extend ViewedAt = GeneratedAt
| project-away GeneratedAt;
let acc_genSnapshot = genSnapshot
| summarize GeneratedAt = min(GeneratedAt) by tenantId
| make-series n = dcount(tenantId) on GeneratedAt from bin(publicPreview, 1d) to now() step 1d
| mv-expand n, GeneratedAt
| extend GeneratedAt = todatetime(GeneratedAt)
| sort by GeneratedAt asc
| serialize acc_GeneratedAt = row_cumsum(toint(n))
| project-away n;
let getSnapshot = Aggregation
| where Action == 'GetSnapshotAPICalled'
| join kind=inner genSnapshot on tenantId, reportName
| where TIMESTAMP > GeneratedAt
| summarize ViewedAt = min(TIMESTAMP) by tenantId, reportName
| union backfillView;
let acc_getSnapshot = getSnapshot
| summarize ViewedAt = min(ViewedAt) by tenantId
| make-series n = dcount(tenantId) on ViewedAt from bin(publicPreview, 1d) to now() step 1d
| mv-expand n, ViewedAt
| extend ViewedAt = todatetime(ViewedAt)
| sort by ViewedAt asc
| serialize acc_ViewedAt = row_cumsum(toint(n))
| project-away n;
let createOfferGuid = Aggregation
| where Action == 'CreateSucceeded' and isnotempty(offerGuid);
let updateOfferGuid = Aggregation
| where Action == 'UpdateSucceeded' and isnotempty(offerGuid);
let offerGUID = union updateOfferGuid, createOfferGuid
| join kind=inner getSnapshot on tenantId, reportName
| summarize ConfiguredofferGuidAt = min(TIMESTAMP) by tenantId, reportName, offerGuid
| summarize arg_max(ConfiguredofferGuidAt, *) by tenantId, reportName
| mv-expand offerGuid = split(offerGuid, ',')
| project tenantId, reportName, offerGuid = trim(@"\s", tostring(offerGuid)), ConfiguredofferGuidAt;
let acc_offerGuid = offerGUID
| summarize FirstConfiguredat = arg_min(ConfiguredofferGuidAt, *) by tenantId
| make-series n = dcount(tenantId) on FirstConfiguredat from bin(publicPreview, 1d) to now() step 1d
| mv-expand n, FirstConfiguredat
| extend FirstConfiguredat = todatetime(FirstConfiguredat)
| sort by FirstConfiguredat asc
| serialize acc_FirstConfiguredat = row_cumsum(toint(n))
| project-away n;
let appCompliance = Aggregation
| where Action == 'ReportDownloadedByAppCompliance'
| join kind=leftouter offerGUID on $left.offerGuid == $right.offerGuid
| where isnotempty(tenantId1) and TIMESTAMP > ConfiguredofferGuidAt
| summarize ReportRequestedAt = min(TIMESTAMP) by tenantId1, reportName, offerGuid;
let acc_AppCompliance = appCompliance
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
// Aggregation
// |  where    Action =='CreateSucceeded' or Action =='UpdateSucceeded'
// genSnapshot| summarize  take_any(*) by tenantId|join  kind=rightanti (cluster('mcatprodkusto.westus3.kusto.windows.net').database('GenevaDb').GenerateSnapshot
// |where tenantId !in (cluster('mcatprodkusto.westus3.kusto.windows.net').database('GenevaDb').ACATTeamInternalTenantIds) and tenantId !=''
// | summarize  GeneratedAt=min(TIMESTAMP) by tenantId,reportName|summarize take_any(*) by tenantId) on tenantId
```

2) HTTP Response
- Description: Hourly counts of API calls grouped by method + canonicalized target API and httpStatusCode over the last 7 days, excluding internal tenants. Adapt by changing the time window, adding httpStatusCode ranges, or focusing on particular API routes.
```kusto
HttpResponse
| where TIMESTAMP > ago(7d) and tenantId !in (ACATTeamInternalTenantIds)
| extend  targetAPI = iff(targetUri startswith '/providers/Microsoft.AppComplianceAutomation/reports/',
                          '/providers/Microsoft.AppComplianceAutomation/reports/', targetUri),
         hour = bin(TIMESTAMP, 1h)
| extend  targetAPIandMethod = strcat(httpMethod, ' ', targetAPI)
| summarize count() by targetAPIandMethod, hour, httpStatusCode
```

3) Snapshot failure
- Description: Same base as HTTP Response query; labeled for tracking snapshot-related API usage. Adapt by filtering to failure classes (e.g., httpStatusCode >= 400) or narrowing to snapshot-related endpoints in targetAPI.
```kusto
HttpResponse
| where TIMESTAMP > ago(7d) and tenantId !in (ACATTeamInternalTenantIds)
| extend  targetAPI = iff(targetUri startswith '/providers/Microsoft.AppComplianceAutomation/reports/',
                          '/providers/Microsoft.AppComplianceAutomation/reports/', targetUri),
         hour = bin(TIMESTAMP, 1h)
| extend  targetAPIandMethod = strcat(httpMethod, ' ', targetAPI)
| summarize count() by targetAPIandMethod, hour, httpStatusCode
```

4) Compliance Report
- Description: Same structure as HTTP Response; use it to monitor compliance report endpoints. Adapt similarly by focusing on report routes or status classes.
```kusto
HttpResponse
| where TIMESTAMP > ago(7d) and tenantId !in (ACATTeamInternalTenantIds)
| extend  targetAPI = iff(targetUri startswith '/providers/Microsoft.AppComplianceAutomation/reports/',
                          '/providers/Microsoft.AppComplianceAutomation/reports/', targetUri),
         hour = bin(TIMESTAMP, 1h)
| extend  targetAPIandMethod = strcat(httpMethod, ' ', targetAPI)
| summarize count() by targetAPIandMethod, hour, httpStatusCode
```

5) Active ISV and Guest
- Description: Daily distinct ISVs and active ISVs (action endswith "Sent") from ExtTelemetry for ACAT’s portal extension; guests are ISVs minus active. Excludes internal tenants via a cross-cluster cohort. Adapt by changing the extension name, day binning, or active criteria.
```kusto
let tenantInfo = cluster('u360sec').database('KPIData').Product360CustomerSubscriptions
| distinct Customer_TenantId, Customer_TenantName, Customer_TenantDisplayName;
ExtTelemetry
| where extension == "Microsoft_Azure_AppComplianceAutomation"
  and tenantId !in (cluster('mcatprodkusto.westus3.kusto.windows.net').database('GenevaDb').ACATTeamInternalTenantIds())
| extend reportName = tostring(parse_json(data)["reportName"]), day = bin(TIMESTAMP, 1d)
| summarize nISVs = dcount(tenantId), nActiveISVs = dcountif(tenantId, action endswith "Sent") by day
| extend nGuests = nISVs - nActiveISVs
```

6) Error count
- Description: Hourly error counts by errorType over the last 14 days (based on PreciseTimeStamp filter, binned by TIMESTAMP). Adapt by filtering errorType sets or adding dimension breakdowns.
```kusto
Error
| where PreciseTimeStamp >= now(-14d)
| extend  hourlyTime = bin(TIMESTAMP, 1h)
| summarize count(), TimeStamp = min(TIMESTAMP) by errorType, hourlyTime
```

7) Azure Portal Usage
- Description: Same as the Error count query (label suggests portal usage view). Adapt by changing the source table to a portal usage table (if available) or retaining error tracking as-is.
```kusto
Error
| where PreciseTimeStamp >= now(-14d)
| extend  hourlyTime = bin(TIMESTAMP, 1h)
| summarize count(), TimeStamp = min(TIMESTAMP) by errorType, hourlyTime
```

8) ISV Retention
- Description: Computes retention across 30-day anchored bins starting at public preview. Defines onboarding as the first GetSnapshotAPICalled after a snapshot generation (with pre-preview backfill), then counts tenants’ subsequent activity windows. It excludes a fixed set of tenants. Adapt by changing the anchor date, bin size, or exclusion cohort.
```kusto
let publicPreview = datetime('2022-12-13');
let genSnapshot = Aggregation
| where Action == 'GenSnapshotSucceeded'
| where tenantId !in ("972de77a-552f-45ca-96ef-0b3d91110db4", "800398a7-3ef1-41fe-824a-687dc6e0b1d9", "49511fb1-4af8-4eb3-a4f3-0a1b3038b64d", "46fbc19c-18f2-4c28-b879-c08e01afd40f", "6a1c431e-7372-45c4-a780-555e7ae1a2ac", "217e0081-c272-40b1-921c-94745eba0eed", "b16461d0-d7eb-46c1-b3c1-86f2a55c9042", "e947416c-06b4-4fa6-9889-aeea22e44139", "ef05883f-b8b3-4031-8ffc-1dc84f621dff", "bbdddcf8-f6b5-4d8b-aa8b-8db0c66d0c6a", "f70e581e-768a-4fd4-b088-7540530f8377", "b2c0b6ec-0036-4fe9-b222-f419713a4772", "06f05128-8a81-4bc7-95e8-81e3de737730", "b80aed20-39d5-494e-aa8d-15ad0a398251", "e6fb4586-2f1f-45af-9af8-a5a101a6c3de", "a8667cb7-9598-42ad-b1af-37fa62890999", "f765057c-99a1-48ca-8149-00c006fba601")
| summarize GeneratedAt = min(TIMESTAMP) by tenantId, reportName;
let backfillView = genSnapshot
| where GeneratedAt < publicPreview
| extend ViewedAt = GeneratedAt
| project-away GeneratedAt;
let ISVonboard = Aggregation
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
    from publicPreview - 30d to bin_at(now() + 30d, 30d, publicPreview) step 30d
    by bin_at(OnboardedAt, 30d, publicPreview)
| mv-expand nISVs, lastActiveAt
| extend lastActiveAt = todatetime(lastActiveAt), nISVs = toint(nISVs)
| where lastActiveAt >= OnboardedAt
| extend Nago = toint(format_timespan(lastActiveAt - OnboardedAt, 'd'))
| sort by OnboardedAt, lastActiveAt
| serialize acc = row_cumsum(nISVs, OnboardedAt != prev(OnboardedAt))
```

## Reasoning Notes (only if uncertain)
- Timezone: Not provided; we assume UTC. If sources write local times, alignment may be needed.
- ACATTeamInternalTenantIds appears both as a table and as a function call (ACATTeamInternalTenantIds()); we treat either form as a cohort exclusion, but the exact implementation may differ per environment.
- Aggregation table’s cluster: Queries use Aggregation unqualified, but the table list points to acattelemetry.eastus.kusto.windows.net; ensure your default database context or qualify explicitly.
- Active definition: action endswith "Sent" in ExtTelemetry is used as the active signal; if action taxonomy changes, the filter must be updated.
- offerGuid normalization: offerGuid can be CSV; trimming via trim(@"\s", ...) is used—this trims backslash and 's' characters as well; if strict whitespace trimming is needed, consider replace or regex functions.
- Public preview anchor: Different analyses use different anchors (e.g., 2022-12-10 vs 2022-12-13); choose one per scenario and keep it consistent across bins.
- HTTP route canonicalization: Using the reports/ prefix to normalize; if additional API families matter, extend the iff mapping (or use parse_path()).
- Error table time columns: Filters use PreciseTimeStamp but grouping uses TIMESTAMP; confirm both columns exist and represent the same event time basis.
- Tenant dimensions: tenantInfo is sometimes defined but not used; if needed, join on Customer_TenantId and deduplicate tenants before counting.
- Backfill logic: Backfill assumes pre-preview views are treated as views; validate business intent for inclusion/exclusion around anchor dates.

## Canonical Tables

Notes on schemas
- We attempted to retrieve exact schemas via ADX tools, but access was denied or objects could not be resolved across clusters/databases. As a result, the column lists below are derived from columns explicitly referenced in the provided queries and should be treated as partial. When access is available, refresh these sections by running getschema on each table.
- Timezone and data refresh latency are unknown. When analyzing “today,” beware of partial ingestion and prefer complete prior days.

---

### Table: Aggregation (cluster('acattelemetry.eastus.kusto.windows.net').database('<unknown>'))
- Priority: Normal
- What this table represents: Event log (fact) of ACAT workflow actions, such as GenSnapshotSucceeded, GetSnapshotAPICalled, CreateSucceeded, UpdateSucceeded, and ReportDownloadedByAppCompliance. Zero rows for a time span typically indicate no activity/events, not deletions.
- Freshness expectations: Unknown. Use daily or hourly bins based on query needs; avoid assuming same-day completeness without verifying ingestion.
- When to use:
  - Build adoption funnels: snapshot generated → viewed → offer configured → compliance report requested.
  - Compute cumulative counts (make-series + row_cumsum) for onboarding/activation metrics.
  - Attribute earliest timestamps per tenant for milestones (arg_min/arg_max).
  - Join by tenantId and reportName to connect generation and consumption.
  - Track offer GUID configuration and subsequent compliance report usage.
- When to avoid:
  - Root-cause API failures (prefer HttpResponse for status codes or Error for exceptions).
  - Portal-specific telemetry (prefer ExtTelemetry).
- Similar tables & how to choose:
  - HttpResponse: API-level outcomes (HTTP status); use when you need status codes for REST calls.
  - Error: service exceptions and error types; use for error classification timelines.
  - ExtTelemetry: portal extension telemetry; use for portal traffic and behavior.
- Common Filters:
  - Action in ('GenSnapshotSucceeded','GetSnapshotAPICalled','CreateSucceeded','UpdateSucceeded','ReportDownloadedByAppCompliance')
  - TIMESTAMP time windows (e.g., > ago(7d))
  - tenantId not in ACATTeamInternalTenantIds
  - reportName present and used to correlate generation and subsequent accesses
  - offerGuid present and later split/mv-expand
- Schema retrieval status: Not accessible via tool; columns below are derived from queries.
- Table columns:
  
  | Column      | Type     | Description or meaning |
  |-------------|----------|------------------------|
  | TIMESTAMP   | unknown  | Event time used for time filtering, binning, and milestone sequencing. |
  | Action      | unknown  | Event type; examples include GenSnapshotSucceeded, GetSnapshotAPICalled, CreateSucceeded, UpdateSucceeded, ReportDownloadedByAppCompliance. |
  | tenantId    | unknown  | ISV/customer tenant identifier; key for grouping and de-duplicating. |
  | reportName  | unknown  | Report name used to correlate generation and subsequent accesses. |
  | offerGuid   | unknown  | Offer identifier; configured via Create/Update, can be comma-separated and later split/mv-expand. |
- Column Explain:
  - TIMESTAMP: Binning (1d/1h) and sequencing for funnels; used to compute first/earliest events per tenant.
  - Action: Drives scenario-specific filters; each funnel step is keyed off a distinct action value.
  - tenantId: Primary grouping key for dcount and onboarding/activation progression.
  - reportName: Ensures you only count views that post-date the corresponding generation.
  - offerGuid: Enables mapping from configured offers to subsequent compliance report requests.

---

### Table: HttpResponse
- Priority: Normal
- What this table represents: API call outcomes (fact) with targetUri, httpMethod, and httpStatusCode. Zero rows for a period indicate no matching API traffic.
- Freshness expectations: Unknown. Queries commonly use TIMESTAMP > ago(7d) and bin by hour (1h).
- When to use:
  - Status distribution per API/method (e.g., 2xx/4xx/5xx) over time.
  - Detect spikes in specific endpoints or methods.
  - Build hourly trend charts of response counts by API and code.
- When to avoid:
  - Tracking logical ACAT workflow milestones (Aggregation is better).
  - Portal-specific extension telemetry (ExtTelemetry).
- Similar tables & how to choose:
  - Error: Use when you need exception/errorType context rather than HTTP codes.
  - Aggregation: Use when the question is about business events (snapshots, views, offer config).
- Common Filters:
  - TIMESTAMP > ago(7d)
  - tenantId not in ACATTeamInternalTenantIds
  - Transform targetUri into a normalized targetAPI (e.g., reports path prefix)
  - Hourly binning via bin(TIMESTAMP, 1h)
- Schema retrieval status: Not accessible via tool; columns below are derived from queries.
- Table columns:
  
  | Column         | Type     | Description or meaning |
  |----------------|----------|------------------------|
  | TIMESTAMP      | unknown  | Event time used for time filters and hourly binning. |
  | tenantId       | unknown  | Tenant identifier; filtered against internal tenant list. |
  | targetUri      | unknown  | Request path; normalized to targetAPI for grouping (e.g., '/providers/Microsoft.AppComplianceAutomation/reports/'). |
  | httpMethod     | unknown  | HTTP method (GET/POST/etc.). |
  | httpStatusCode | unknown  | Numeric status code for success/failure grouping. |
- Column Explain:
  - TIMESTAMP: Time filters and hourly charting.
  - tenantId: Exclude internal traffic via not-in ACATTeamInternalTenantIds.
  - targetUri: Normalize and group APIs; useful to aggregate related endpoints.
  - httpMethod: Combine with API to produce targetAPIandMethod.
  - httpStatusCode: Key dimension for reliability analysis.

---

### Table: Error
- Priority: Normal
- What this table represents: Error/exception log (fact) with errorType and timestamps. Zero rows for a window mean no logged errors.
- Freshness expectations: Unknown. Patterns show 14-day windows with hourly binning.
- When to use:
  - Hourly error counts by errorType.
  - Correlate service regressions across time.
- When to avoid:
  - HTTP-level diagnostics (prefer HttpResponse).
  - Business event funnels (Aggregation).
- Similar tables & how to choose:
  - HttpResponse: Status-code oriented; Error is exception/error-type oriented.
  - Aggregation: Not for errors; use to follow user/business events.
- Common Filters:
  - PreciseTimeStamp >= now(-14d)
  - Hourly binning: bin(TIMESTAMP, 1h)
- Schema retrieval status: Not accessible via tool; columns below are derived from queries.
- Table columns:
  
  | Column            | Type     | Description or meaning |
  |-------------------|----------|------------------------|
  | PreciseTimeStamp  | unknown  | High-precision timestamp used for time range filters. |
  | TIMESTAMP         | unknown  | Event time used for hourly binning and min(TIMESTAMP). |
  | errorType         | unknown  | Error category/type used to group counts. |
- Column Explain:
  - PreciseTimeStamp: Primary filter for the 14-day lookback.
  - TIMESTAMP: Used for hourly bucketing and display.
  - errorType: Aggregation dimension for error trends.

---

### Table: ExtTelemetry (cluster('azportalpartnerrow.westus.kusto.windows.net').database('<unknown>'))
- Priority: Normal
- What this table represents: Azure Portal extension telemetry (fact) capturing UI/extension actions for Microsoft_Azure_AppComplianceAutomation. Zero rows indicate no extension activity.
- Freshness expectations: Unknown. Usage aggregated by day with bin(TIMESTAMP, 1d).
- When to use:
  - Count ISVs vs. active ISVs for the portal extension.
  - Compute guests = dcount(tenantId) – dcountif(... endswith 'Sent').
- When to avoid:
  - Server-side API reliability (HttpResponse) or backend business events (Aggregation).
- Similar tables & how to choose:
  - Aggregation: Use for backend workflow events; ExtTelemetry is for portal usage behavior.
  - HttpResponse/Error: Use for reliability/exception analysis, not UI telemetry.
- Common Filters:
  - extension == "Microsoft_Azure_AppComplianceAutomation"
  - tenantId not in cluster('mcatprodkusto.westus3.kusto.windows.net').database('GenevaDb').ACATTeamInternalTenantIds()
  - Daily binning via bin(TIMESTAMP, 1d)
- Schema retrieval status: Not accessible via tool; columns below are derived from queries.
- Table columns:
  
  | Column     | Type     | Description or meaning |
  |------------|----------|------------------------|
  | TIMESTAMP  | unknown  | Event time; binned daily for trend metrics. |
  | extension  | unknown  | Portal extension name; filter equals Microsoft_Azure_AppComplianceAutomation. |
  | tenantId   | unknown  | Tenant identifier for dcount metrics. |
  | action     | unknown  | Telemetry action; used with endswith 'Sent' to identify active ISVs. |
  | data       | unknown  | JSON payload; parse_json(data)['reportName'] used to extract reportName. |
- Column Explain:
  - extension: Scopes telemetry to the ACAT portal extension.
  - tenantId: Used to compute distinct ISVs and active subsets.
  - action: Suffix 'Sent' marks active interactions.
  - data: JSON source for report-related fields.
  - TIMESTAMP: Drives daily trend calculations.

---

### Table: ACATTeamInternalTenantIds
- Priority: Normal
- What this table represents: Internal control list (fact or function output) of ACAT team tenant IDs used to exclude internal traffic from analyses.
- Freshness expectations: Unknown; treat as reference data that changes infrequently.
- When to use:
  - Exclude internal telemetry: tenantId not in (ACATTeamInternalTenantIds) or not in ACATTeamInternalTenantIds().
  - Join or anti-join patterns to remove internal tenants.
- When to avoid:
  - Any business metric that should include internal testing (only include if explicitly needed).
- Similar tables & how to choose:
  - None noted; this is the canonical exclusion list for internal tenants.
- Common Filters:
  - tenantId !in (ACATTeamInternalTenantIds) or tenantId !in (ACATTeamInternalTenantIds())
- Schema retrieval status: Not accessible via tool; usage indicates it returns a set of tenant IDs. It may be defined as either a table or a function in GenevaDb.
- Table columns:
  
  | Column   | Type     | Description or meaning |
  |----------|----------|------------------------|
  | tenantId | unknown  | Tenant ID to be excluded from customer-facing analyses. |
- Column Explain:
  - tenantId: Use with not-in to filter out internal traffic across all queries.

---

### Table: Product360CustomerSubscriptions (cluster('u360sec.kusto.windows.net').database('KPIData'))
- Priority: Normal
- What this table represents: Reference mapping (dimension) of customer tenant identity and display metadata for U360/Product360. Zero rows for a join indicates no match for a given tenant.
- Freshness expectations: Unknown; use cautiously for “current snapshot” name/display attributes.
- When to use:
  - Enrich tenantId with Customer_TenantName and Customer_TenantDisplayName.
  - Build tenantInfo lookup for de-duplicated tenants.
- When to avoid:
  - As a source of ACAT events (Aggregation/HttpResponse/Error carry event data).
- Similar tables & how to choose:
  - None provided; this is the canonical U360 subscription dimension used in queries.
- Common Filters:
  - Distinct selection of Customer_TenantId/Name/DisplayName.
  - Exclusion rules on tenant names (e.g., exclude “Contoso”) when needed.
- Schema retrieval status: Access denied for cross-cluster getschema; columns below are derived from queries.
- Table columns:
  
  | Column                    | Type     | Description or meaning |
  |---------------------------|----------|------------------------|
  | Customer_TenantId         | unknown  | Tenant identifier to join with ACAT event tenantId. |
  | Customer_TenantName       | unknown  | Customer tenant name text. |
  | Customer_TenantDisplayName| unknown  | Display-friendly tenant name. |
- Column Explain:
  - Customer_TenantId: Key used to enrich Aggregation-derived tenantId.
  - Customer_TenantName/DisplayName: Human-readable metadata for reporting/labeling.

---

Guidance and patterns to reuse
- Time windows and binning:
  - Default to conservative windows (7–14 days) and hourly/daily bins depending on scenario.
  - For “current day,” validate ingestion completeness or shift to complete prior day.
- Internal traffic exclusion:
  - Consistently exclude ACATTeamInternalTenantIds to avoid skewing reliability/usage metrics.
- Funnel construction:
  - Use Aggregation with earliest-event summarizations (min TIMESTAMP) per tenant and reportName.
  - Enforce temporal ordering by comparing event times (e.g., view time > generation time).
  - Use make-series followed by mv-expand and row_cumsum to compute cumulative activation.
- Cross-source joins:
  - For portal usage (ExtTelemetry), filter by the specific extension name, then aggregate by day.
  - For tenant enrichment, join Aggregation to Product360CustomerSubscriptions on tenantId ↔ Customer_TenantId.
- Scaling tips:
  - Start with smaller time ranges (7d, 14d) and add top N or summarize early to manage cost.
  - Add where isnotempty(...) guards before joins to reduce cardinality and cost.
- Access notes:
  - Several schemas were not retrievable due to access limitations or cross-cluster resolution. Once access is granted, run getschema on each table and update the column lists accordingly.