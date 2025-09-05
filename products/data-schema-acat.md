
# App Compliance Automation Tool for Microsoft 365 – Product and Data Overview

## 1. Product Overview

App Compliance Automation Tool for Microsoft 365 (ACAT) is a service in Azure portal that helps simplify the compliance journey for any app that consumes Microsoft 365 customer data and is published via Partner Center. It's an application-centric compliance automation tool that helps you complete Microsoft 365 Certification with greater ease and convenience.

With this tool, you'll quickly be able to define the compliance boundary for your applications, monitor the compliance results automatically, and complete the compliance audit more easily. The compliance boundary is the cloud infrastructure that supports delivery of the app and any backend systems that the app communicating with.

In addition to providing a faster track towards Microsoft 365 Certification, ACAT can help you in various compliance scenarios for Microsoft 365 applications:

Detailed view and remediation steps for Microsoft 365 Certification responsibilities.
Automatic daily reports of compliance assessments to keep your applications compliant continuously.
Security and compliance best practices that can be used as guidance in the early phase of your application lifecycle.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**: ACAT
- **Kusto Cluster**: `https://acattelemetry.eastus.kusto.windows.net/`
- **Kusto Database**: `Aggregation`
- **Primary Metrics**: 

## 3. Table Schemas in Azure Data Explorer

### 3.1 Table `Aggregation`

| Column Name       | Type              | Csl Type   | Description               |
|-------------------|-------------------|------------|---------------------------|
| PreciseTimeStamp  | System.DateTime   | datetime   | Precise timestamp of the record |
| TIMESTAMP         | System.DateTime   | datetime   | General timestamp         |
| reportName        | System.String     | string     | Name of the report        |
| offerGuid         | System.String     | string     | Unique identifier for the marketplace offer (M365 app) in Partner Center. |
| tenantId          | System.String     | string     | Identifier for the tenant |
| Action            | System.String     | string     | Type of action recorded   |

### 3.2 Table `PortalTelemetry`

| Column Name | Type            | Csl Type | Description                        |
|-------------|------------------|----------|------------------------------------|
| TIMESTAMP   | System.DateTime  | datetime | Timestamp of the telemetry event   |
| source      | System.String    | string   | Origin or source of the telemetry  |
| action      | System.String    | string   | Action performed                   |
| data        | System.String    | string   | Additional data related to the action |
| context     | System.String    | string   | Contextual information             |
| tenantId    | System.String    | string   | Identifier for the tenant          |
| sessionId   | System.String    | string   | Session identifier                 |

## 4. Common Analytical Scenarios

- **ISV**: Identified by tenantId.
- **ACAT Compliance Report**: The reportName should not be duplicated for one specific ISV, but could be same for different ISVs. Therefore, the identifier of ACAT compliance report should be tenantId plus reportName together.
- **Action**: The ISV actions with ACAT compliance report. This is also used to learn ISV funnel in ACAT. Here are the values of 'Action' Column and their meaning. 
  - CreateSucceeded: The compliance report is created successfully. 
  - GenSnapshotSucceeded: The ACAT generates compliance assessments snapshot for the specific report successfully. 
  - GetSnapshotAPICalled: The ISV gets the compliance assessments of a specific report successfully. 
  - UpdateSucceeded: The ISV updates the settings of a specific report successfully. 
  - ReportDownloadedByAppCompliance: The ISV submits the certification review in Paretner Center and then the reviewer downloads report in Partner Center. 
  - DeleteSucceeded: The ISV deletes a specific report successfully.
- **Offer GUID**: Unique identifier for the marketplace offer (M365 app) in Partner Center. This will be valid if the ISV update the report settings with GUIDs from Partner Center. 

## 5. Common Filters and Definitions

### 5.1 External Release Usage

Filter the external release usage of ACAT by public preview launch date.

```kusto 
let publicPreview=datetime('2022-12-10');
```

### 5.2 Internal User 

Filter the internal user by tenant name

```kusto 
let tenantInfo = cluster('u360sec').database('KPIData').Product360CustomerSubscriptions
| distinct Customer_TenantId, Customer_TenantName, Customer_TenantDisplayName;
tenantInfo
| where Customer_TenantName !has "Contoso"
```

### 5.3 Backfill Data

Always union the backfill data to make sure there is no lost. For example,

```kusto 
let publicPreview=datetime('2022-12-10');
let tenantInfo = cluster('u360sec').database('KPIData').Product360CustomerSubscriptions
| distinct Customer_TenantId, Customer_TenantName, Customer_TenantDisplayName;
let genSnapshot = Aggregation 
| where  Action =='GenSnapshotSucceeded'
| join kind=leftouter  tenantInfo on $left.tenantId==$right.Customer_TenantId
| where  Customer_TenantName !has ""Contoso""
| summarize  GeneratedAt=min(TIMESTAMP) by tenantId,reportName;
let backfillView = genSnapshot
| where GeneratedAt <datetime('2022-12-13')
| extend  ViewedAt=GeneratedAt
| project-away GeneratedAt;
let getSnapshot = Aggregation
| where Action =='GetSnapshotAPICalled'
| join kind=inner  genSnapshot on tenantId,reportName
| where TIMESTAMP >GeneratedAt
| summarize  ViewedAt=min(TIMESTAMP) by tenantId,reportName
| union backfillView;
```

### 5.4 Offer GUID Configure Success

The user may configure offer GUID when creating compliance report or update setting later. 

```kusto 
let createOfferGuid=Aggregation|where  Action =='CreateSucceeded' and   isnotempty(offerGuid) ;
let updateOfferGuid=Aggregation| where  Action =='UpdateSucceeded' and   isnotempty(offerGuid) ;
let offerGUID= union updateOfferGuid, createOfferGuid;
```

## 6. Notes and Considerations

- All timestamps are in **UTC**.
- Data refresh is **daily** with ~2-hour delay.
- Always exclude usage from internal user and usage before public preview to focus on external customer behavior.
