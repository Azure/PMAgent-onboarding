# Teams Toolkit - Product and Data Overview Template

## 1. Product Overview

Teams Toolkit product onboarding schema for OKR 2.2: F5 success rate analysis by version and project type. This draft captures the product’s event model, core definitions, reusable views, and canonical tables to enable PMAgent to interpret product-specific data correctly.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**:
Teams Toolkit
- **Product Nick Names**: 
**[TODO]Data_Engineer**: Fill in commonly used short names or abbreviations for the product to help PMAgent accurately recognize the target product from user conversations.
- **Kusto Cluster**:
Unknown (pending confirmation; please provide your ADX cluster name)
- **Kusto Database**:
Unknown (pending confirmation; please provide your ADX database name)
- **Access Control**:
**[TODO] Data Engineer**: If this product’s data has high confidentiality concerns, please specify the allowed **groups/users** here. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.  

-----

# OKR 2.2: F5 success rate - Kusto Query Playbook

## Overview
- Product summary: By version and project type
- Main cluster: Unknown
- Main database: Unknown

## Conventions & Assumptions

### Time semantics
- Observed time columns:
  - ClientTimestamp (VSC events)
  - eventTimestamp (CLI events)
  - ClientTimestampUtc (VS events)
  - Derived: Timestamp (canonical, used for aggregation and alignment), FirstDebugTime, FirstSuccessTime, LastEventTime, StartTime
- Canonical Time Column: Timestamp
  - Pattern: Project early/last event times into a unified `Timestamp` for downstream summarization.
  - Example aliasing:
    - VS: extend Timestamp = LastEventTime
    - VSC/CLI: summarize Timestamp = minif(ClientTimestamp, Name == 'debug-all') and minif(eventTimestamp, Name == 'preview')
- Typical windows:
  - Completeness gate with LatestFirstDebugTime = now() - 3d to allow users time to complete first successful debug. Queries include only projects whose first debug happened earlier than this threshold.
- bin() usage: Not present in provided queries
- Timezone:
  - VS events use UTC explicitly (ClientTimestampUtc).
  - VSC/CLI event timezones are unknown; treat as UTC by default and align to UTC when cross-client aggregating.

### Freshness & Completeness Gates
- Completeness:
  - LatestFirstDebugTime = now() - 3d ensures projects have at least 3 days since their first debug before classifying as blocked (IsNeverSuccess).
- Infinite duration cap:
  - DurationThreshold = 60min used as an upper bound for “DurationBeforeSuccess” when the project never succeeded in VS flows.
- Recommended effective end time pattern:
  - If ingestion completeness is unknown for the current day, prefer using data up to now() - 1d (or last completed day/week) when reporting trends.

### Joins & Alignment
- Frequent keys:
  - ProjectId (primary project entity key)
  - ClientName (‘VSC’, ‘CLI’, ‘VS’)
  - IsTestTool (boolean distinguishing Test Tool runs)
- Common join kinds:
  - join kind=leftouter: Align sessions with first-success, first-debug, and project type; preserves unmatched rows for blocked projects.
  - join kind=inner: Enforce presence of ProjectType (from v5ProjectType) when classifying.
- Post-join hygiene:
  - Normalize error types: reclassify certain error codes from ‘user’ to ‘system’.
  - Drop intermediate counters: project-away DebugAllCount, TestToolCount.
  - Version normalization: split and recompose version strings to sortable format (VersionMajorMinor, padded minor).

### Filters & Idioms
- Version filters:
  - VSC: ExtensionVersion in (v5Versions)
  - CLI: cliversion in (v5Versions) plus regex \d+\.\d+\.\d+$
  - VS: filter out ExeVersion in (v5Versions) and only ExeVersion >= 17.6
- Correlation/session hygiene:
  - Require non-empty session id: isnotempty(CorrelationId) and CorrelationId != 'no-session-id'
- Legacy project exclusion:
  - Exclude v4 projects via ProjectId !in (V4Projects) (where v4 derives from ExtensionVersion startswith '4.')
- Internal/test data:
  - Internal users from InternalMachineIds lists (VSC/CLI) or Properties['context.default.vs.core.user.isvslogininternal'] == 'true' (VS).
  - Test tool detection: environment id allowlist (Properties['env.teamsfx_env'] in (...)) sets IsTestTool.
- Error-specific exclusions:
  - VSC: exclude a subset of Ext.PrerequisitesValidationError failures (specifically node.js failure or transform to more granular error codes).
  - CLI: exclude Ext.PrerequisitesValidationError failures from blocked calculations.

### Cross-cluster/DB & Sharding
- Cross-source union:
  - union merges VSC and CLI sessions after normalizing keys and timestamps (v5AllValidSessions).
  - Separate pipeline for VS, merged at the end into the combined dataset.
- Pattern: union → normalize keys/time → summarize.

### Table classes
- Facts (events):
  - teamsfx_all (VSC events)
  - teamsfx_all_cli (CLI events)
  - teamsfx_all_vs (VS events)
- Dimensions/reference:
  - v5Versions (allowlist of versions)
  - v5ProjectType (project capabilities → type classification)
  - InternalMachineIds (internal cohort)
- Usage guidance:
  - Use Facts for event-level analysis (per-session/per-correlation).
  - Use Dimensions to filter valid versions, map capabilities to ProjectType, and separate internal/test users.

### Important Mapping
- Project type classification:
  - Capabilities/AppType strings → categories: Bot, Tab, ME, Copilot, Unknown
  - Multiple regex buckets define the category mapping.
- Error type reclassification:
  - Certain error codes (datatable UserErrorCodeShouldBeSystemType) should be treated as system not user.
- Release type:
  - VS: derive from ChannelId (Release → Stable; Preview → Preview; else IntPreview).
  - VSC/CLI: ClientVersion regex used to identify Prerelease vs Stable.

## Entity & Counting Rules (Core Definitions)
- Entity model:
  - Project: ProjectId
  - Session: CorrelationId (within a client context)
  - Client: ClientName in {VSC, CLI, VS}
- Grouping levels:
  - Per ProjectId and ClientName (with IsTestTool split)
  - Version-level views: VSC/CLI use normalized ClientVersion; VS use VersionMajorMinor.
- Business definitions (as implemented):
  - First Success: FirstSuccessTime = min(Timestamp) across all versions for a project-client (DebugSuccess or IsSuccess for relevant event names).
  - Blocked/never success: IsNeverSuccess = isempty(FirstSuccessTime); sessions before FirstSuccessTime are considered “attempts before first success” and contribute errors/success-rate tags.
  - Success rate dataset: rows tagged with Tag = 'SuccessRate', enriched with IsNeverSuccess, version, project type, client channel, and error type (if present). The rate metric itself is typically computed in downstream BI (not directly summarized in these queries).

## Views (Reusable Layers)

- DurationThreshold
  - Purpose: Cap duration when no success occurred (set “infinite” duration to 60 minutes).
  - Query:
```kusto
let DurationThreshold = 60min;
```

- LatestFirstDebugTime
  - Purpose: Completeness gate; require first debug to be older than 3 days to classify as blocked.
  - Query:
```kusto
let LatestFirstDebugTime = now() - 3d;
```

- UserErrorCodeShouldBeSystemType
  - Purpose: Map specific user-type error codes to system-type in BI reporting.
  - Query:
```kusto
let UserErrorCodeShouldBeSystemType = datatable(ErrorCode: string)
[
'Ext.PortsConflictError',
'Ext.PrerequisitesSideloadingDisabledError',
'fileCreateOrUpdateEnvironmentFile.MissingEnvironmentVariablesError',
'script.ScriptExecutionError',
'aadAppCreate.HttpClientError',
'AppStudioPlugin.TeamsAppCreateConflict',
'devToolInstall.TestToolInstallationError',
'Ext.DebugServiceFailedBeforeStartError',
'devToolInstall.FuncInstallationError',
'<REDACTED: user-file-path>',
'm365.iwt',
'script.v0r',
'AadAppClient.ClientSecretNotAllowed',
'Ext.DevTunnelOperationError',
'Log In.UserError',
'Log In._ur',
'AppStudioPlugin.ManifestValidationFailed',
'Log In.LoginTimeout',
'Ext.DebugTestToolFailedToStartError',
'botAadAppCreate.HttpClientError',
'AppStudioPlugin.TeasmAppNotExists',
'Core.ConcurrentError',
'coordinator.CancelProvision',
'Core.TrustCertificateCancelError',
'aadAppUpdate.HttpClientError',
'teamsApp.MissingEnvironmentVariablesError',
'Ext.PrerequisitesNoM365AccountError',
'M365.PackageServiceError',
'coordinator.M365TenantIdNotMatchError',
'ConfigManager.InvalidYamlSchemaError',
'Core.TrustCertificateError',
'Ext.TunnelEnvError',
'AppStudioPlugin.InvalidTeamsAppId',
'm365.InternalError',
'armDeploy.DeployArmError',
'botFrameworkCreate.MissingEnvironmentVariablesError',
'Ext.PrerequisitesValidationError',
'AadAppClient.DeleteOrUpdatePermissionFailed',
'devToolInstall.FilePermissionError',
'core.MissingRequiredFileError'
];
```

- V4Projects
  - Purpose: Identify v4 projects to exclude.
  - Inputs: teamsfx_all
  - Query:
```kusto
let V4Projects = teamsfx_all
| where ExtensionVersion startswith '4.'
| extend ProjectId = tostring(Properties['project-id'])
| distinct ProjectId;
```

- VSCv5AllValidSessions
  - Purpose: Normalize VSC v5 debug/metadata/lifecycle events per session; derive success, timestamp, error fields, and internal/test flags.
  - Inputs: teamsfx_all, v5Versions, InternalMachineIds
  - Query:
```kusto
let VSCv5AllValidSessions = teamsfx_all
| extend VersionArr = split(ExtensionVersion, '.')
| extend Version = toint(VersionArr[0])*10000 + toint(VersionArr[1])*100 + toint(VersionArr[2])
| where ExtensionName == 'ms-teams-vscode-extension' and ExtensionVersion in (v5Versions)
| extend 
    Name = tostring(split(EventName, '/')[1]),
    ProjectId = tostring(Properties['project-id']),
    Duration = todouble(Measures['duration']) * 1s,
    IsSuccess = Properties['success'] == 'yes',
    CheckResults = parse_json(tostring(Properties['debug-check-results-safe'])),
    CorrelationId = tostring(Properties['correlation-id'])
| where isnotempty(CorrelationId) and CorrelationId != 'no-session-id'
| where (Name == 'debug-all') or (Name == 'debug-prerequisites') or (Name == 'metadata') or (Name == 'lifecycle-execution')
| summarize 
    (_, ClientVersion, MachineId) = arg_min(ClientTimestamp, ExtensionVersion, VSCodeMachineId),
    ProjectId = take_any(tostring(Properties['project-id'])),
    Timestamp = minif(ClientTimestamp, Name == 'debug-all'),
    Duration = take_anyif(todouble(Measures['duration']) * 1s, Name == 'debug-all'),
    DebugSuccess = maxif(IsSuccess, Name == 'debug-all'),
    Platform = take_any(Platform),
    DebugAllCount = countif(Name == 'debug-all'),
    ErrorCode = take_anyif(tostring(Properties['error-code']), Name == 'debug-all'),
    ErrorMessage = take_anyif(tostring(Properties['error-message']), Name == 'debug-all'),
    ErrorType = take_anyif(tostring(Properties['error-type']), Name == 'debug-all'),
    LastEventName = take_anyif(tostring(Properties['debug-last-event-name']), Name == 'debug-all'),
    PrereqsTaskArgs = take_anyif(tostring(Properties['debug-task-args']), Name == 'debug-prerequisites'),
    PrereqsSuccess = maxif(IsSuccess, Name == 'debug-prerequisites'),
    CheckResults = take_anyif(parse_json(tostring(Properties['debug-check-results-safe'])), Name == 'debug-prerequisites'),
    TaskInfo = take_anyif(tostring(Properties['debug-prelaunch-task-info']), Name == 'debug-all'),
    LifeCycleFailure = make_set_if(tostring(Properties['lifecycle']), Name == 'lifecycle-execution'),
    MetadataCount = countif(Name == 'metadata'),
    TestToolCount = countif(Properties['env.teamsfx_env'] in ('f3cc87f78b21d53dcccd34b6dd0c2e8679cb5e6ea3ad600e2689015ce100825a', 'c585cf93fbff733898e3e58c67bc041f02e3b0c913993a1cba724f45b9d321f1'))
    by CorrelationId
| where DebugAllCount > 0
| where not(not(DebugSuccess) and ErrorCode == 'Ext.PrerequisitesValidationError' and CheckResults['Node.js'].result == 'failed')
| extend
    IsSuccess = DebugSuccess,
    IsTestTool = TestToolCount > 0,
    ErrorCode = tostring(
            case(
                ErrorCode != 'Ext.PrerequisitesValidationError', ErrorCode,
                CheckResults['ports occupancy'].result == 'failed', strcat_delim('.', CheckResults['ports occupancy'].source, 'PortsConflictError'),
                CheckResults['Microsoft 365 Account'].result == 'failed', strcat_delim('.', CheckResults['Microsoft 365 Account'].source, CheckResults['Microsoft 365 Account'].errorCode),
                ErrorCode
            )
        )
| extend IsInternalUser = MachineId in (InternalMachineIds) 
| project-away DebugAllCount, TestToolCount
| extend ClientName = 'VSC';
```

- CLIv5AllValidSessions
  - Purpose: Normalize CLI v5 preview/metadata/lifecycle events per session; derive success, timestamp, error fields, and internal flags.
  - Inputs: teamsfx_all_cli, v5Versions, InternalMachineIds
  - Query:
```kusto
let CLIv5AllValidSessions = teamsfx_all_cli
| extend VersionArr = split(cliversion, '.')
| extend Version = toint(VersionArr[0])*10000 + toint(VersionArr[1])*100 + toint(VersionArr[2])
| where cliversion in (v5Versions) and cliversion matches regex @'\d+\.\d+\.\d+$'
| extend 
    Name = tostring(split(name, '/')[1]),
    ProjectId = tostring(properties['project-id']),
    Duration = todouble(measures['duration']) * 1s,
    IsSuccess = properties['success'] == 'yes',
    CheckResults = parse_json(tostring(properties['debug-check-results-safe'])),
    CorrelationId = tostring(properties['correlation-id'])
| where isnotempty(CorrelationId) and CorrelationId != 'no-session-id'
| where (Name == 'preview') or (Name == 'preview-prerequisites') or (Name == 'metadata') or (Name == 'lifecycle-execution')
| summarize 
    (_, ClientVersion, MachineId) = arg_min(eventTimestamp, cliversion, machineid),
    ProjectId = take_any(tostring(properties['project-id'])),
    Timestamp = minif(eventTimestamp, Name == 'preview'),
    Duration = take_anyif(todouble(measures['duration']) * 1s, Name == 'preview'),
    DebugSuccess = maxif(IsSuccess, Name == 'preview'),
    DebugAllCount = countif(Name == 'preview'),
    ErrorCode = take_anyif(tostring(properties['error-code']), Name == 'preview'),
    ErrorMessage = take_anyif(tostring(properties['error-message']), Name == 'preview'),
    ErrorType = take_anyif(tostring(properties['error-type']), Name == 'preview'),
    MetadataCount = countif(Name == 'metadata'),
    ManifestMetadataProperties = take_anyif(properties, Name == 'metadata' and isnotempty(properties['manifest.id']))
    by CorrelationId
| where DebugAllCount > 0
| where not(not(DebugSuccess) and ErrorCode == 'Ext.PrerequisitesValidationError')
| extend IsSuccess = DebugSuccess
| extend IsInternalUser = MachineId in (InternalMachineIds)
| project-away DebugAllCount
| extend ClientName = 'CLI';
```

- V5AllTemplateAndSample, V5ProjectTypes, V5AllProjectType
  - Purpose: Determine project version and type (Bot/Tab/ME/Copilot) from templates/samples and capabilities.
  - Inputs: teamsfx_all, teamsfx_all_cli, v5Versions, v5ProjectType
  - Queries:
```kusto
let VSCV5TemplateAndSample = teamsfx_all
| extend Name = tostring(split(EventName, '/')[1])
| where ExtensionName == 'ms-teams-vscode-extension' 
    and ExtensionVersion in (v5Versions)
    and (Name == 'create-project' or Name == 'download-sample')
| extend ProjectId = tostring(Properties['new-project-id'])
| summarize (_, ClientVersion) = arg_min(ClientTimestamp, ExtensionVersion) by ProjectId, ExtensionVersion
| extend ClientName = 'VSC'
| project ProjectId, ClientVersion, ClientName;

let CLIV5TemplateAndSample = teamsfx_all_cli
| where cliversion in (v5Versions) and cliversion matches regex @'\d+\.\d+\.\d+$'
| extend Name = tostring(split(name, '/')[1])
| where Name == 'create-project' or Name == 'download-sample'
| extend ProjectId = tostring(properties['new-project-id'])
| summarize (_, ClientVersion) = arg_min(eventTimestamp, cliversion) by ProjectId, cliversion
| extend ClientName = 'CLI'
| project ProjectId, ClientVersion, ClientName;

let V5AllTemplateAndSample = VSCV5TemplateAndSample
| union CLIV5TemplateAndSample;

let V5ProjectTypes = v5ProjectType
| where Capabilities != ''
| project ProjectId, AppType=tostring(Capabilities);

let V5AllProjectType = V5AllTemplateAndSample
| join kind = inner V5ProjectTypes on ProjectId
| summarize by ProjectId, AppType, ClientVersion
| extend LowerAppType = tolower(AppType)
| extend ProjectType = tostring(
        case(
            LowerAppType matches regex @'\b(bot|adaptive-card|notification|botandmessageextension|tabnonssoandbot)\b', 'Bot',
            LowerAppType matches regex @'\b(tab|dashboard|todo-list|sso-launch-page|hello-world-in-meeting|graph-toolkit|graph-connector-app|live-share-dice-roller|outlook-add-in-set-signature|share-now|intelligent-data-chart-generator)\b', 'Tab',
            LowerAppType matches regex @'\b(message-extension|messageextension|msgext|search-app|link-unfurling|npm-search-connector-m365)\b', 'ME',
            LowerAppType matches regex @'\b(copilot|api-plugin|declarative-agent)\b', 'Copilot',
            'Unknown'
        )
    )
| project ProjectId, ProjectType, ClientVersion;
```

- v5AllValidSessions, ProjectFirstDebugSessions, ProjectFirstSuccessSessions, v5AllBeforeFirstSuccessSessions, v5ProjectData, v5Errors, v5SuccessRate
  - Purpose: Build per-project-per-client session dataset prior to first success, classify blocked projects, and tag error/success-rate rows.
  - Dependencies: VSCv5AllValidSessions, CLIv5AllValidSessions, LatestFirstDebugTime, V5AllProjectType, V4Projects, UserErrorCodeShouldBeSystemType
  - Queries:
```kusto
let v5AllValidSessions = VSCv5AllValidSessions
| union CLIv5AllValidSessions;

let ProjectFirstDebugSessions = v5AllValidSessions
| summarize FirstDebugTime = min(Timestamp) by ProjectId, IsTestTool;

let ProjectFirstSuccessSessions = v5AllValidSessions
| where DebugSuccess
| summarize FirstSuccessTime = min(Timestamp) by ProjectId, ClientName, IsTestTool;

let v5AllBeforeFirstSuccessSessions = v5AllValidSessions
| join kind=leftouter ProjectFirstSuccessSessions on ProjectId, ClientName, IsTestTool
| extend IsNeverSuccess = isempty(FirstSuccessTime)
| where IsNeverSuccess or Timestamp <= FirstSuccessTime
| join kind=leftouter ProjectFirstDebugSessions on ProjectId, IsTestTool
| where FirstDebugTime < LatestFirstDebugTime
| join kind=leftouter V5AllProjectType on ProjectId
| extend ProjectType = iff(isempty(ProjectType), 'Unknown', ProjectType)
| where ProjectId !in (V4Projects);

let v5ProjectData = v5AllBeforeFirstSuccessSessions
| summarize
    IsNeverSuccess = take_any(IsNeverSuccess),
    (Timestamp, ErrorCode, ErrorMessage, ErrorType) = arg_max(Timestamp, ErrorCode, ErrorMessage, ErrorType),
    (_, ClientVersion, MachineId, IsInternalUser) = arg_min(Timestamp, ClientVersion, MachineId, IsInternalUser),
    ProjectType = take_any(ProjectType)
    by ProjectId, ClientName, IsTestTool
| extend ClientVersionArr = split(ClientVersion, '.')
| extend VersionMajor = tostring(ClientVersionArr[0]), VersionMinor = tostring(ClientVersionArr[1]), VersionPatch = tostring(ClientVersionArr[2])
| extend VersionMinor = iif(toint(VersionMinor) < 10, strcat('0', VersionMinor), VersionMinor)
| extend ClientVersion = strcat(tostring(VersionMajor), '.', tostring(VersionMinor), '.', VersionPatch)
| extend ErrorType = iif(ErrorType == 'user' and ErrorCode in (UserErrorCodeShouldBeSystemType), 'system', ErrorType)
| project ProjectId, ClientName, ClientVersion, MachineId, IsInternalUser, IsTestTool, Timestamp, ErrorCode, ErrorMessage, IsNeverSuccess, ProjectType, ErrorType;

let v5Errors = v5ProjectData
| where IsNeverSuccess
| extend Tag = 'error';

let v5SuccessRate = v5ProjectData
| extend Tag = 'SuccessRate';
```

- VSDataClean, VSDebugProjectEvents, VSPrepareDebugEvents, VSAllDebugEvents, VSProjectFirstSuccessSessions, VSAllBeforeFirstSuccessEvents, VSResult, VSErrors, VSSuccessRate
  - Purpose: VS pipeline for prepare/debug, derive first success, aggregate attempts, then tag error/success-rate rows.
  - Inputs: teamsfx_all_vs, v5Versions, v5ProjectType, DurationThreshold
  - Queries:
```kusto
let TimestampInfinity = datetime(2100, 1, 1);

let VSDataClean = teamsfx_all_vs 
| where ExeVersion !in (v5Versions)
| extend VersionMajor = toint(split(ExeVersion, '.')[0]), VersionMinor = toint(split(ExeVersion, '.')[1])
| where VersionMajor >= 17 and VersionMinor >= 6 
| extend 
    Name = tostring(Properties['vs.teamsfx.name']),
    CorrelationId = tostring(Properties['vs.teamsfx.core.correlation-id']),
    ProjectId = tostring(Properties['vs.teamsfx.core.project-id']),
    IsInternalUser = Properties['context.default.vs.core.user.isvslogininternal'] == 'true',
    IsManifestMetadata = isnotempty(Properties['vs.teamsfx.core.manifest.id']),
    CoreEvent = tostring(Properties['vs.teamsfx.core.event']),
    NewProjectId = tostring(Properties['vs.teamsfx.core.new-project-id']),
    Component = iff(Properties['vs.teamsfx.core.component'] == 'fx-resource-dotnet', 'fx-resource-frontend-hosting', tostring(Properties['vs.teamsfx.core.component'])),
    ErrorMessage = tostring(Properties['reserved.datamodel.fault.description']),
    IsManifestEvent = EventName == 'vs/teamsfx/core' and Properties['vs.teamsfx.core.event'] == 'metadata' and isnotempty(Properties['vs.teamsfx.core.manifest.id'])
| where isnotempty(ProjectId)
| distinct ClientTimestampUtc, CoreEvent, CorrelationId, Component, EventName, EventId, ExeVersion, MacAddressHash, IsInternalUser, Name, NewProjectId, ProjectId, ErrorMessage, ChannelId, IsManifestMetadata
| extend MachineId = MacAddressHash
| extend VersionMajor = tostring(split(ExeVersion, '.')[0]), VersionMinor = tostring(split(ExeVersion, '.')[1])
| extend VersionMinor = iif(toint(VersionMinor) < 10, strcat('0', VersionMinor), VersionMinor)
| extend VersionMajorMinor = strcat(VersionMajor, '.', VersionMinor);

let VSDebugProjectEvents = VSDataClean
| where isnotempty(ProjectId)
| where Name == 'DebugProject'
| order by ClientTimestampUtc asc
| serialize 
| extend StartTime = iff(prev(ProjectId, 1) == ProjectId and prev(EventName, 1) == 'vs/teamsfx/command/start' and prev(Name, 1) == 'DebugProject', prev(ClientTimestampUtc, 1), datetime(null))
| extend IsSuccess = EventName == 'vs/teamsfx/command'
| extend StartEventNotFound = isempty(StartTime)
| extend Duration = (ClientTimestampUtc - StartTime);

let VSPrepareDebugEvents = VSDataClean
| where isnotempty(ProjectId)
| where Name == 'Debug'
| order by ClientTimestampUtc asc
| serialize 
| extend StartTime = iff(prev(ProjectId, 1) == ProjectId and prev(EventName, 1) == 'vs/teamsfx/command/start' and prev(Name, 1) == 'Debug', prev(ClientTimestampUtc, 1), datetime(null))
| extend IsSuccess = EventName == 'vs/teamsfx/command'
| extend StartEventNotFound = isempty(StartTime)
| extend Duration = (ClientTimestampUtc - StartTime);

let VSAllDebugEvents = VSDebugProjectEvents
| union VSPrepareDebugEvents;

let VSProjectFirstSuccessSessions = VSDebugProjectEvents
| summarize 
    (FirstSuccessTime, FirstSuccessExeVersion) = arg_min(iff(IsSuccess, ClientTimestampUtc, TimestampInfinity+1d), ExeVersion),
    LastDebugTime = max(ClientTimestampUtc)
    by ProjectId
| extend FirstSuccessTime = iff(FirstSuccessTime > TimestampInfinity, datetime(null), FirstSuccessTime);

let VSAllBeforeFirstSuccessEvents = VSAllDebugEvents
| join kind=leftouter v5ProjectType on ProjectId
| extend ProjectType = tostring(
    case(
            Capabilities matches regex @'\b(bot|adaptive-card|notification|botandmessageextension|tabnonssoandbot)\b', 'Bot',
            Capabilities matches regex @'\b(tab|dashboard|todo-list|sso-launch-page|hello-world-in-meeting|graph-toolkit|graph-connector-app|live-share-dice-roller|outlook-add-in-set-signature|share-now|intelligent-data-chart-generator)\b', 'Tab',
            Capabilities matches regex @'\b(message-extension|messageextension|msgext|search-app|link-unfurling|npm-search-connector-m365)\b', 'ME',
            Capabilities matches regex @'\b(copilot|api-plugin|declarative-agent)\b', 'Copilot',
            'Unknown'
        )
)
| join kind=leftouter VSProjectFirstSuccessSessions on ProjectId
| extend IsNeverSuccess = isempty(FirstSuccessTime)
| where IsNeverSuccess or ClientTimestampUtc <= FirstSuccessTime;

let VSResult = VSAllBeforeFirstSuccessEvents
| summarize 
    FirstSuccessTime = take_any(FirstSuccessTime),
    LastTime = take_any(LastDebugTime),
    FirstSuccessVersion = take_any(FirstSuccessExeVersion),
    IsNeverSuccess = take_any(IsNeverSuccess),
    Duration = sum(Duration),
    DebugStartCount = countif(EventName == 'vs/teamsfx/command/start' and Name == 'DebugProject'),
    DebugCount = countif(EventName == 'vs/teamsfx/command' and Name == 'DebugProject'),
    PrepareStartCount = countif(EventName == 'vs/teamsfx/command/start' and Name == 'Debug'),
    PrepareCount = countif(EventName == 'vs/teamsfx/command' and Name == 'Debug'),
    (LastEventTime, LastEventName, LastCommandName, LastErrorMessage, MachineId, IsInternalUser) = arg_max(ClientTimestampUtc, EventName, Name, ErrorMessage, MachineId, IsInternalUser),
    ProjectType = take_any(ProjectType)
    by ProjectId, VersionMajorMinor, ChannelId
| extend DurationBeforeSuccess = iff(IsNeverSuccess, DurationThreshold, Duration)
| extend LastErrorMessage = iff(isempty(LastErrorMessage), '<User successfully prepared but never hits F5>', LastErrorMessage)
| extend Timestamp = LastEventTime
| extend ErrorType = iif(IsNeverSuccess, 'system', '');

let VSErrors = VSResult
| where IsNeverSuccess
| project ClientName = 'VS', ClientVersion = VersionMajorMinor, ProjectId, MachineId, IsInternalUser, ErrorMessage = LastErrorMessage, ErrorCode = substring(LastErrorMessage, 0, 50), Tag = 'error', ChannelId, ProjectType, Timestamp, ErrorType;

let VSSuccessRate = VSResult
| project ClientName = 'VS', ClientVersion = VersionMajorMinor, ProjectId, MachineId, IsInternalUser, Tag = 'SuccessRate', IsNeverSuccess, ChannelId, ProjectType, Timestamp, ErrorType;
```

- Final union (dataset for BI)
  - Purpose: Merge VSC/CLI and VS datasets, derive ReleaseType, normalize IsTestTool default.
  - Query:
```kusto
union v5Errors, v5SuccessRate,
    VSErrors, VSSuccessRate
| extend ReleaseType = 
    iff(ClientName == 'VS', 
        iff(ChannelId contains_cs 'Release', 'Stable',
            iff(ChannelId contains_cs 'Preview', 'Preview', 'IntPreview')),
        iff(ClientVersion matches regex '\d+\.\d+\.\d{3,10}', 'Prerelease', 'Stable'))
| extend IsTestTool = iff(isempty(IsTestTool), false, IsTestTool)
```

## Query Building Blocks (Copy-paste snippets, contains snippets and description)

- Time window template
  - Description: Use this when you need a conservative window and to avoid current-day incompleteness. Parameterize start/end and optionally enforce a completeness gate for first debug.
  - Snippet:
```kusto
// Parameters
let StartTime = datetime(<YYYY-MM-DD>);
let EndTime = datetime(<YYYY-MM-DD>); // Prefer now() - 1d if ingestion lag unknown
let LatestFirstDebugTime = now() - 3d; // Completeness gate

<YourFactTable>
| where <EventTimeColumn> between (StartTime .. EndTime)
| join kind=leftouter ProjectFirstDebugSessions on ProjectId
| where FirstDebugTime < LatestFirstDebugTime
```

- Join template
  - Description: Standard alignment across project, client, and test-tool cohort; preserves blocked (never-success) projects.
  - Snippet:
```kusto
<SessionFacts>
| join kind=leftouter ProjectFirstSuccessSessions on ProjectId, ClientName, IsTestTool
| extend IsNeverSuccess = isempty(FirstSuccessTime)
| where IsNeverSuccess or Timestamp <= FirstSuccessTime
| join kind=leftouter V5AllProjectType on ProjectId
| extend ProjectType = iff(isempty(ProjectType), 'Unknown', ProjectType)
```

- De-dup pattern
  - Description: Use arg_min/arg_max and distinct when raw logs can duplicate, and to extract earliest/latest event context.
  - Snippet:
```kusto
// VS raw de-dup
VSDataClean = teamsfx_all_vs
| where isnotempty(ProjectId)
| distinct ClientTimestampUtc, CoreEvent, CorrelationId, Component, EventName, EventId, ExeVersion, MacAddressHash, IsInternalUser, Name, NewProjectId, ProjectId, ErrorMessage, ChannelId, IsManifestMetadata;

// Earliest success and last seen
<Events>
| summarize 
    (FirstSuccessTime, FirstSuccessVersion) = arg_min(iff(IsSuccess, EventTime, datetime(2100-01-01)+1d), Version),
    LastEventTime = max(EventTime)
    by ProjectId
```

- Important filters
  - Description: Cohort hygiene and exclusions that appear frequently.
  - Snippets:
```kusto
// Version allowlist
| where ExtensionVersion in (v5Versions)

// CLI version format guard
| where cliversion matches regex @'\d+\.\d+\.\d+$'

// Require valid session id
| where isnotempty(CorrelationId) and CorrelationId != 'no-session-id'

// Exclude legacy v4 projects
| where ProjectId !in (V4Projects)

// Internal users (VSC/CLI)
| extend IsInternalUser = MachineId in (InternalMachineIds)

// Internal users (VS)
| extend IsInternalUser = Properties['context.default.vs.core.user.isvslogininternal'] == 'true'

// Exclude certain prerequisite failures
| where not(not(DebugSuccess) and ErrorCode == 'Ext.PrerequisitesValidationError')
```

- Important Definitions
  - Description: Apply these consistently when reporting.
  - Snippets:
```kusto
// Project type mapping via capabilities
let V5ProjectTypes = v5ProjectType
| where Capabilities != ''
| project ProjectId, AppType=tostring(Capabilities);

let ProjectTypeMap = V5ProjectTypes
| extend LowerAppType = tolower(AppType)
| extend ProjectType = tostring(
        case(
            LowerAppType matches regex @'\b(bot|adaptive-card|notification|botandmessageextension|tabnonssoandbot)\b', 'Bot',
            LowerAppType matches regex @'\b(tab|dashboard|todo-list|sso-launch-page|hello-world-in-meeting|graph-toolkit|graph-connector-app|live-share-dice-roller|outlook-add-in-set-signature|share-now|intelligent-data-chart-generator)\b', 'Tab',
            LowerAppType matches regex @'\b(message-extension|messageextension|msgext|search-app|link-unfurling|npm-search-connector-m365)\b', 'ME',
            LowerAppType matches regex @'\b(copilot|api-plugin|declarative-agent)\b', 'Copilot',
            'Unknown'
        )
    )
| project ProjectId, ProjectType;

// Error type normalization
| extend ErrorType = iif(ErrorType == 'user' and ErrorCode in (UserErrorCodeShouldBeSystemType), 'system', ErrorType)

// Release type classification
| extend ReleaseType = 
    iff(ClientName == 'VS', 
        iff(ChannelId contains_cs 'Release', 'Stable',
            iff(ChannelId contains_cs 'Preview', 'Preview', 'IntPreview')),
        iff(ClientVersion matches regex '\d+\.\d+\.\d{3,10}', 'Prerelease', 'Stable'))
```

- ID parsing/derivation
  - Description: Standard property extraction from nested telemetry payloads.
  - Snippets:
```kusto
// VSC
| extend ProjectId = tostring(Properties['project-id']),
         ClientVersion = ExtensionVersion,
         CorrelationId = tostring(Properties['correlation-id']),
         ErrorCode = tostring(Properties['error-code']),
         ErrorMessage = tostring(Properties['error-message'])

// CLI
| extend ProjectId = tostring(properties['project-id']),
         ClientVersion = cliversion,
         CorrelationId = tostring(properties['correlation-id']),
         ErrorCode = tostring(properties['error-code']),
         ErrorMessage = tostring(properties['error-message'])

// VS
| extend ProjectId = tostring(Properties['vs.teamsfx.core.project-id']),
         ErrorMessage = tostring(Properties['reserved.datamodel.fault.description'])
```

- Sharded union
  - Description: Merge VSC and CLI (same logical schema, different sources) and then aggregate per-project.
  - Snippet:
```kusto
let v5AllValidSessions = VSCv5AllValidSessions
| union CLIv5AllValidSessions
| project ProjectId, ClientName, ClientVersion, MachineId, IsInternalUser, IsTestTool, Timestamp, ErrorCode, ErrorMessage, DebugSuccess, ErrorType;

// Downstream: first success, attempts before success, and classification
```

## Example Queries (with explanations)

1) VSC v5 Valid Sessions
- Description: Builds per-correlation VSC session aggregates for debug, prerequisites, metadata, and lifecycle, applies filters for valid session ids, version allowlist, and prerequisite error exclusions. Produces success flag, timestamp for debug-all, and normalized error fields.
```kusto
let VSCv5AllValidSessions = teamsfx_all
| extend VersionArr = split(ExtensionVersion, '.')
| extend Version = toint(VersionArr[0])*10000 + toint(VersionArr[1])*100 + toint(VersionArr[2])
| where ExtensionName == 'ms-teams-vscode-extension' and ExtensionVersion in (v5Versions)
| extend 
    Name = tostring(split(EventName, '/')[1]),
    ProjectId = tostring(Properties['project-id']),
    Duration = todouble(Measures['duration']) * 1s,
    IsSuccess = Properties['success'] == 'yes',
    CheckResults = parse_json(tostring(Properties['debug-check-results-safe'])),
    CorrelationId = tostring(Properties['correlation-id'])
| where isnotempty(CorrelationId) and CorrelationId != 'no-session-id'
| where (Name == 'debug-all') or (Name == 'debug-prerequisites') or (Name == 'metadata') or (Name == 'lifecycle-execution')
| summarize 
    (_, ClientVersion, MachineId) = arg_min(ClientTimestamp, ExtensionVersion, VSCodeMachineId),
    ProjectId = take_any(tostring(Properties['project-id'])),
    Timestamp = minif(ClientTimestamp, Name == 'debug-all'),
    Duration = take_anyif(todouble(Measures['duration']) * 1s, Name == 'debug-all'),
    DebugSuccess = maxif(IsSuccess, Name == 'debug-all'),
    Platform = take_any(Platform),
    DebugAllCount = countif(Name == 'debug-all'),
    ErrorCode = take_anyif(tostring(Properties['error-code']), Name == 'debug-all'),
    ErrorMessage = take_anyif(tostring(Properties['error-message']), Name == 'debug-all'),
    ErrorType = take_anyif(tostring(Properties['error-type']), Name == 'debug-all'),
    LastEventName = take_anyif(tostring(Properties['debug-last-event-name']), Name == 'debug-all'),
    PrereqsTaskArgs = take_anyif(tostring(Properties['debug-task-args']), Name == 'debug-prerequisites'),
    PrereqsSuccess = maxif(IsSuccess, Name == 'debug-prerequisites'),
    CheckResults = take_anyif(parse_json(tostring(Properties['debug-check-results-safe'])), Name == 'debug-prerequisites'),
    TaskInfo = take_anyif(tostring(Properties['debug-prelaunch-task-info']), Name == 'debug-all'),
    LifeCycleFailure = make_set_if(tostring(Properties['lifecycle']), Name == 'lifecycle-execution'),
    MetadataCount = countif(Name == 'metadata'),
    TestToolCount = countif(Properties['env.teamsfx_env'] in ('f3cc87f78b21d53dcccd34b6dd0c2e8679cb5e6ea3ad600e2689015ce100825a', 'c585cf93fbff733898e3e58c67bc041f02e3b0c913993a1cba724f45b9d321f1'))
    by CorrelationId
| where DebugAllCount > 0
| where not(not(DebugSuccess) and ErrorCode == 'Ext.PrerequisitesValidationError' and CheckResults['Node.js'].result == 'failed')
| extend
    IsSuccess = DebugSuccess,
    IsTestTool = TestToolCount > 0,
    ErrorCode = tostring(
            case(
                ErrorCode != 'Ext.PrerequisitesValidationError', ErrorCode,
                CheckResults['ports occupancy'].result == 'failed', strcat_delim('.', CheckResults['ports occupancy'].source, 'PortsConflictError'),
                CheckResults['Microsoft 365 Account'].result == 'failed', strcat_delim('.', CheckResults['Microsoft 365 Account'].source, CheckResults['Microsoft 365 Account'].errorCode),
                ErrorCode
            )
        )
| extend IsInternalUser = MachineId in (InternalMachineIds) 
| project-away DebugAllCount, TestToolCount
| extend ClientName = 'VSC';
```

2) CLI v5 Valid Sessions
- Description: Similar to VSC but for CLI preview flow; filters valid version formats and excludes prerequisite failures. Produces per-correlation session aggregates.
```kusto
let CLIv5AllValidSessions = teamsfx_all_cli
| extend VersionArr = split(cliversion, '.')
| extend Version = toint(VersionArr[0])*10000 + toint(VersionArr[1])*100 + toint(VersionArr[2])
| where cliversion in (v5Versions) and cliversion matches regex @'\d+\.\d+\.\d+$'
| extend 
    Name = tostring(split(name, '/')[1]),
    ProjectId = tostring(properties['project-id']),
    Duration = todouble(measures['duration']) * 1s,
    IsSuccess = properties['success'] == 'yes',
    CheckResults = parse_json(tostring(properties['debug-check-results-safe'])),
    CorrelationId = tostring(properties['correlation-id'])
| where isnotempty(CorrelationId) and CorrelationId != 'no-session-id'
| where (Name == 'preview') or (Name == 'preview-prerequisites') or (Name == 'metadata') or (Name == 'lifecycle-execution')
| summarize 
    (_, ClientVersion, MachineId) = arg_min(eventTimestamp, cliversion, machineid),
    ProjectId = take_any(tostring(properties['project-id'])),
    Timestamp = minif(eventTimestamp, Name == 'preview'),
    Duration = take_anyif(todouble(measures['duration']) * 1s, Name == 'preview'),
    DebugSuccess = maxif(IsSuccess, Name == 'preview'),
    DebugAllCount = countif(Name == 'preview'),
    ErrorCode = take_anyif(tostring(properties['error-code']), Name == 'preview'),
    ErrorMessage = take_anyif(tostring(properties['error-message']), Name == 'preview'),
    ErrorType = take_anyif(tostring(properties['error-type']), Name == 'preview'),
    MetadataCount = countif(Name == 'metadata'),
    ManifestMetadataProperties = take_anyif(properties, Name == 'metadata' and isnotempty(properties['manifest.id']))
    by CorrelationId
| where DebugAllCount > 0
| where not(not(DebugSuccess) and ErrorCode == 'Ext.PrerequisitesValidationError')
| extend IsSuccess = DebugSuccess
| extend IsInternalUser = MachineId in (InternalMachineIds)
| project-away DebugAllCount
| extend ClientName = 'CLI';
```

3) Project Type Classification
- Description: Maps projects to Bot/Tab/ME/Copilot categories using capabilities from v5ProjectType after capturing template/sample origin.
```kusto
let V5ProjectTypes = v5ProjectType
| where Capabilities != ''
| project ProjectId, AppType=tostring(Capabilities);

let V5AllProjectType = (teamsfx_all
    | extend Name = tostring(split(EventName, '/')[1])
    | where ExtensionName == 'ms-teams-vscode-extension' and ExtensionVersion in (v5Versions)
        and (Name == 'create-project' or Name == 'download-sample')
    | extend ProjectId = tostring(Properties['new-project-id'])
    | summarize (_, ClientVersion) = arg_min(ClientTimestamp, ExtensionVersion) by ProjectId, ExtensionVersion
    | extend ClientName = 'VSC'
    | project ProjectId, ClientVersion, ClientName)
| union (teamsfx_all_cli
    | where cliversion in (v5Versions) and cliversion matches regex @'\d+\.\d+\.\d+$'
    | extend Name = tostring(split(name, '/')[1])
    | where Name == 'create-project' or Name == 'download-sample'
    | extend ProjectId = tostring(properties['new-project-id'])
    | summarize (_, ClientVersion) = arg_min(eventTimestamp, cliversion) by ProjectId, cliversion
    | extend ClientName = 'CLI'
    | project ProjectId, ClientVersion, ClientName)
| join kind = inner V5ProjectTypes on ProjectId
| summarize by ProjectId, AppType, ClientVersion
| extend LowerAppType = tolower(AppType)
| extend ProjectType = tostring(
        case(
            LowerAppType matches regex @'\b(bot|adaptive-card|notification|botandmessageextension|tabnonssoandbot)\b', 'Bot',
            LowerAppType matches regex @'\b(tab|dashboard|todo-list|sso-launch-page|hello-world-in-meeting|graph-toolkit|graph-connector-app|live-share-dice-roller|outlook-add-in-set-signature|share-now|intelligent-data-chart-generator)\b', 'Tab',
            LowerAppType matches regex @'\b(message-extension|messageextension|msgext|search-app|link-unfurling|npm-search-connector-m365)\b', 'ME',
            LowerAppType matches regex @'\b(copilot|api-plugin|declarative-agent)\b', 'Copilot',
            'Unknown'
        )
    )
| project ProjectId, ProjectType, ClientVersion;
```

4) Attempts Before First Success (VSC/CLI)
- Description: Align earliest success per project-client, filter sessions to those before first success (or never-success), apply 3-day first-debug gate, and enrich with project type. Excludes legacy v4 projects.
```kusto
let v5AllValidSessions = VSCv5AllValidSessions | union CLIv5AllValidSessions;
let ProjectFirstSuccessSessions = v5AllValidSessions
| where DebugSuccess
| summarize FirstSuccessTime = min(Timestamp) by ProjectId, ClientName, IsTestTool;
let ProjectFirstDebugSessions = v5AllValidSessions
| summarize FirstDebugTime = min(Timestamp) by ProjectId, IsTestTool;
let v5AllBeforeFirstSuccessSessions = v5AllValidSessions
| join kind=leftouter ProjectFirstSuccessSessions on ProjectId, ClientName, IsTestTool
| extend IsNeverSuccess = isempty(FirstSuccessTime)
| where IsNeverSuccess or Timestamp <= FirstSuccessTime
| join kind=leftouter ProjectFirstDebugSessions on ProjectId, IsTestTool
| where FirstDebugTime < LatestFirstDebugTime
| join kind=leftouter V5AllProjectType on ProjectId
| extend ProjectType = iff(isempty(ProjectType), 'Unknown', ProjectType)
| where ProjectId !in (V4Projects);
```

5) VS Final Aggregation
- Description: Compute durations and counts for VS prepare/debug steps before first success, cap infinite durations at threshold, derive last error message and default error type for never-success rows. Produces per-project aggregates by version and channel.
```kusto
let VSResult = VSAllBeforeFirstSuccessEvents
| summarize 
    FirstSuccessTime = take_any(FirstSuccessTime),
    LastTime = take_any(LastDebugTime),
    FirstSuccessVersion = take_any(FirstSuccessExeVersion),
    IsNeverSuccess = take_any(IsNeverSuccess),
    Duration = sum(Duration),
    DebugStartCount = countif(EventName == 'vs/teamsfx/command/start' and Name == 'DebugProject'),
    DebugCount = countif(EventName == 'vs/teamsfx/command' and Name == 'DebugProject'),
    PrepareStartCount = countif(EventName == 'vs/teamsfx/command/start' and Name == 'Debug'),
    PrepareCount = countif(EventName == 'vs/teamsfx/command' and Name == 'Debug'),
    (LastEventTime, LastEventName, LastCommandName, LastErrorMessage, MachineId, IsInternalUser) = arg_max(ClientTimestampUtc, EventName, Name, ErrorMessage, MachineId, IsInternalUser),
    ProjectType = take_any(ProjectType)
    by ProjectId, VersionMajorMinor, ChannelId
| extend DurationBeforeSuccess = iff(IsNeverSuccess, DurationThreshold, Duration)
| extend LastErrorMessage = iff(isempty(LastErrorMessage), '<User successfully prepared but never hits F5>', LastErrorMessage)
| extend Timestamp = LastEventTime
| extend ErrorType = iif(IsNeverSuccess, 'system', '');
```

6) Combined Dataset for BI
- Description: Merge VSC/CLI and VS success-rate/error datasets, derive ReleaseType and ensure IsTestTool is non-empty. Suitable as the final input to BI or dashboards.
```kusto
union v5Errors, v5SuccessRate,
    VSErrors, VSSuccessRate
| extend ReleaseType = 
    iff(ClientName == 'VS', 
        iff(ChannelId contains_cs 'Release', 'Stable',
            iff(ChannelId contains_cs 'Preview', 'Preview', 'IntPreview')),
        iff(ClientVersion matches regex '\d+\.\d+\.\d{3,10}', 'Prerelease', 'Stable'))
| extend IsTestTool = iff(isempty(IsTestTool), false, IsTestTool)
```

7) Legacy v4 Project Identification
- Description: Identify projects created on V4 to exclude from v5 success-rate computations.
```kusto
let V4Projects = teamsfx_all
| where ExtensionVersion startswith '4.'
| extend ProjectId = tostring(Properties['project-id'])
| distinct ProjectId;
```

## Reasoning Notes (only if uncertain)
- Timezone for ClientTimestamp/eventTimestamp is not explicit; we adopt UTC to align with ClientTimestampUtc and to avoid cross-source skew.
- “Success” for VSC/CLI is derived from Name == 'debug-all'/'preview' and IsSuccess == true; for VS, success is EventName == 'vs/teamsfx/command' on specific steps. We adopt these as the operational definitions because they are consistently summarized as DebugSuccess/IsSuccess.
- The 3-day LatestFirstDebugTime gate appears to prevent premature classification as blocked; we adopt this to improve completeness.
- ReleaseType classification for VSC/CLI relies on a version regex heuristic; we adopt it as implemented and caution that prerelease identification may depend on patch-length convention.
- Project type mapping via regex buckets is domain-specific and incomplete (“To be done” for Outlook Add-In). We adopt existing buckets and keep “Unknown” as the default.
- Error type normalization (user→system) reflects BI reporting needs; we adopt the provided mapping and note that the full set may evolve.
- Internal user identification: VS has a property, VSC/CLI rely on a machine id list. We adopt both methods as-is.
- The final dataset tags rows but doesn’t compute percentage success rates; we assume downstream BI computes rates from counts of IsNeverSuccess or successful sessions.

## Canonical Tables

Note on schema discovery
- Attempted to retrieve column schemas using the get_table_schema tool for all tables, but the tables were not accessible in the configured product/cluster (Semantic error: Failed to resolve table or column expression).
- Columns below are inferred strictly from how they are used in the provided queries. Validate in your own cluster/database and update as needed.
- Cluster and database are not specified in the source content; freshness and ingestion cadence are unknown.

Order: All tables are marked Normal priority.

### Table: teamsfx_all
- Priority: Normal
- What this table represents: Event-level telemetry for the VS Code extension “ms-teams-vscode-extension.” Rows appear to represent individual extension events with dynamic Properties and Measures payloads.
- Freshness expectations: Unknown. Avoid using “today” without a buffer; consider a lookback (e.g., 7–14 days) until ingestion latency is verified.
- When to use:
  - Compute F5 (debug) outcomes for VS Code: debug-all, debug-prerequisites, metadata, lifecycle-execution event flows.
  - Derive “first success” vs “never succeeded” for projects using CorrelationId and event sequences.
  - Tag potential test tool sessions using hashed env identifiers in Properties.
  - Normalize/compare versions to filter to v5 releases.
- When to avoid:
  - Visual Studio or CLI analytics (use teamsfx_all_vs or teamsfx_all_cli instead).
  - Aggregates across tooling types without adding the client discriminator (ClientName).
- Similar tables & how to choose:
  - teamsfx_all_cli: for CLI usage.
  - teamsfx_all_vs: for Visual Studio usage.
  - Use teamsfx_all for the VS Code extension only, identified by ExtensionName == 'ms-teams-vscode-extension'.
- Common Filters:
  - ExtensionName == 'ms-teams-vscode-extension'
  - ExtensionVersion in (v5Versions)
  - EventName in: 'ms-teams-vscode-extension/debug-all', '.../debug-prerequisites', '.../metadata', '.../lifecycle-execution'
  - CorrelationId is not empty and != 'no-session-id'
  - Exclude v4-created projects via ProjectId not in V4Projects
- Table columns (inferred; schema fetch failed):
  | Column           | Type     | Description or meaning |
  |------------------|----------|------------------------|
  | ClientTimestamp  | datetime | Client-side event timestamp used for sequencing and min/max calculations. |
  | ExtensionName    | string   | Extension identifier; used to select 'ms-teams-vscode-extension'. |
  | ExtensionVersion | string   | Version string (e.g., x.y.z); parsed for version sorting and v5 filtering. |
  | EventName        | string   | Event path (e.g., ms-teams-vscode-extension/debug-all). |
  | Properties       | dynamic  | JSON map of event details; keys used include 'project-id', 'success', 'debug-check-results-safe', 'correlation-id', 'debug-last-event-name', 'debug-task-args', 'debug-prelaunch-task-info', 'lifecycle'. |
  | Measures         | dynamic  | JSON map of numeric measurements; 'duration' extracted and converted to timespan. |
  | VSCodeMachineId  | string   | Machine identifier for VS Code; used to derive IsInternalUser. |
  | Platform         | string   | Client platform indicator. |
- Column explain:
  - ClientTimestamp: anchor for arg_min/arg_max, first/last event, and time-window filters.
  - ExtensionVersion: compared to v5Versions and normalized for sorting; used to build ClientVersion.
  - EventName and Properties['success']: determine success state of debug-all and prerequisites.
  - Properties['correlation-id']: session grouping key (must be present and not 'no-session-id').
  - Measures['duration']: used to calculate F5 duration.
  - Properties['debug-check-results-safe']: determines error code remapping (e.g., ports occupancy, M365 account).
  - VSCodeMachineId: used against InternalMachineIds to flag internal users.

### Table: teamsfx_all_cli
- Priority: Normal
- What this table represents: Event-level telemetry for the TeamsFX CLI. Rows represent CLI command events with dynamic properties/measures.
- Freshness expectations: Unknown; apply time buffers for near-real-time analysis.
- When to use:
  - Measure CLI “preview” and “preview-prerequisites” flows and success outcomes.
  - Identify first success vs never-success states per project using CorrelationId and event timestamps.
  - Filter out prerelease/invalid versions; parse and sort cliversion.
- When to avoid:
  - VS Code or Visual Studio scenarios (use teamsfx_all or teamsfx_all_vs).
- Similar tables & how to choose:
  - teamsfx_all for VS Code, teamsfx_all_vs for VS; choose by client.
- Common Filters:
  - cliversion in (v5Versions) and matches regex '\d+\.\d+\.\d+$'
  - Name in: 'preview', 'preview-prerequisites', 'metadata', 'lifecycle-execution'
  - properties['correlation-id'] present and != 'no-session-id'
- Table columns (inferred; schema fetch failed):
  | Column         | Type     | Description or meaning |
  |----------------|----------|------------------------|
  | eventTimestamp | datetime | Event timestamp for CLI entries. |
  | cliversion     | string   | CLI version string; used for v5 filtering and sorting. |
  | name           | string   | Event name (e.g., cli/preview). |
  | properties     | dynamic  | JSON map; keys include 'project-id', 'success', 'debug-check-results-safe', 'correlation-id', 'manifest.id'. |
  | measures       | dynamic  | JSON map; 'duration' used to compute timespan. |
  | machineid      | string   | Machine identifier; used with InternalMachineIds for IsInternalUser. |
- Column explain:
  - eventTimestamp: used for ordering and first/last calculations.
  - cliversion: filters to v5 and builds ClientVersion for aggregation.
  - properties['success'] and properties['error-*']: determine success/error metrics for preview.
  - properties['correlation-id']: grouping key for CLI sessions.
  - measures['duration']: duration of the preview operation.

### Table: v5ProjectType
- Priority: Normal
- What this table represents: Project type metadata for v5 projects, mapping a ProjectId to Capabilities (later normalized to Bot/Tab/ME/Copilot/Unknown).
- Freshness expectations: Unknown; treat as reference data that may lag project creation slightly.
- When to use:
  - Join to tag projects with semantic ProjectType for aggregation (success rate by ProjectType).
  - Normalize from Capabilities text into canonical categories via regex mapping.
- When to avoid:
  - If ProjectId is missing or incomplete; ensure you have a joinable ProjectId.
- Similar tables & how to choose:
  - Derived view V5AllProjectType is built from project creation/download events plus v5ProjectType; use v5ProjectType directly when you only need a simple ProjectId -> Capabilities mapping.
- Common Filters:
  - Capabilities != ''
- Table columns (inferred; schema fetch failed):
  | Column     | Type   | Description or meaning |
  |------------|--------|------------------------|
  | ProjectId  | string | Project unique identifier to join with telemetry. |
  | Capabilities | string | Raw capability string used to derive ProjectType (Bot/Tab/ME/Copilot/Unknown). |
- Column explain:
  - ProjectId: foreign key to telemetry tables (teamsfx_all, teamsfx_all_cli, teamsfx_all_vs after extraction).
  - Capabilities: input for regex-based classification of ProjectType.

### Table: teamsfx_all_vs
- Priority: Normal
- What this table represents: Event-level telemetry for Visual Studio Teams Toolkit (VS). Rows include command start/finish signals used to compute durations and success of F5 (DebugProject) and Prepare environment (Debug).
- Freshness expectations: Unknown; avoid using same-day data; consider VS release channels when slicing (ChannelId).
- When to use:
  - Analyze VS F5 pipeline: durations for DebugProject and Debug, first success time, and never-success cohorts.
  - Filter acceptable VS versions (ExeVersion >= 17.6 and not in v5Versions).
  - Classify project types by joining ProjectId to v5ProjectType.
- When to avoid:
  - VS Code or CLI analyses.
- Similar tables & how to choose:
  - teamsfx_all (VS Code) and teamsfx_all_cli (CLI). Use teamsfx_all_vs only for Visual Studio signals.
- Common Filters:
  - ExeVersion !in (v5Versions)
  - VersionMajor >= 17 and VersionMinor >= 6 (derived from ExeVersion)
  - Event pairs: 'vs/teamsfx/command/start' then 'vs/teamsfx/command' for 'DebugProject' and 'Debug'
  - ProjectId non-empty; deduplicate by a set of fields to remove dirty data.
- Table columns (inferred; schema fetch failed):
  | Column             | Type     | Description or meaning |
  |--------------------|----------|------------------------|
  | ClientTimestampUtc | datetime | UTC event timestamp; used to compute durations and first success time. |
  | EventName          | string   | e.g., 'vs/teamsfx/command', 'vs/teamsfx/command/start', 'vs/teamsfx/core'. |
  | EventId            | string   | Event identifier; used in deduplication. Exact type unknown; treat as string. |
  | ExeVersion         | string   | VS executable version; used for filtering and grouping (e.g., 17.6+). |
  | MacAddressHash     | string   | Used as MachineId for user-level grouping. |
  | ChannelId          | string   | VS channel (e.g., Release/Preview) to derive ReleaseType. |
  | Properties         | dynamic  | JSON map; keys used include: 'vs.teamsfx.name' (Name), 'vs.teamsfx.core.correlation-id', 'vs.teamsfx.core.project-id', 'context.default.vs.core.user.isvslogininternal', 'vs.teamsfx.core.manifest.id', 'vs.teamsfx.core.event', 'vs.teamsfx.core.new-project-id', 'vs.teamsfx.core.component', 'reserved.datamodel.fault.description'. |
- Column explain:
  - ClientTimestampUtc: critical for ordering start/end, computing Duration, and first success time.
  - ExeVersion: filters VS population and used to produce VersionMajorMinor.
  - Properties['vs.teamsfx.name']: yields Name ('DebugProject' or 'Debug') for event classification.
  - Properties['vs.teamsfx.core.project-id']: key for joining to project-level views and project types.
  - ChannelId: used to derive ReleaseType (Stable/Preview/IntPreview).
  - Properties['reserved.datamodel.fault.description']: last error for never-success buckets.

### Table: v5Versions
- Priority: Normal
- What this table represents: Reference list of acceptable v5 versions (for VS Code and CLI), used to filter out prereleases or older versions. Also used with toscalar(make_set(Version)).
- Freshness expectations: Unknown; ensure this list is maintained to reflect releases.
- When to use:
  - Filter telemetry rows to v5-supported versions across VS Code and CLI.
  - Exclude VS ExeVersion values that match V5 versions where required.
- When to avoid:
  - Any scenario where version gating isn’t needed.
- Similar tables & how to choose:
  - None provided; this is the canonical allowlist for v5 in this context.
- Common Filters:
  - Column Version in filters and make_set aggregations.
- Table columns (inferred; schema fetch failed):
  | Column  | Type   | Description or meaning |
  |---------|--------|------------------------|
  | Version | string | Allowed version string (e.g., x.y.z) used for v5 filtering. |
- Column explain:
  - Version: primary value used in "in (v5Versions)" filters and building version sets.

### Table: InternalMachineIds
- Priority: Normal
- What this table represents: Reference list of internal machine IDs for excluding or flagging internal usage.
- Freshness expectations: Unknown; verify how often this list updates and whether values are stable.
- When to use:
  - Flag internal users: MachineId in (InternalMachineIds).
  - Slice metrics by IsInternalUser to understand external user behavior.
- When to avoid:
  - When analysis explicitly targets internal testing behavior.
- Similar tables & how to choose:
  - None provided; this is the canonical allowlist for internal machine detection.
- Common Filters:
  - Used in an “in” predicate to derive IsInternalUser boolean.
- Table columns (inferred; schema fetch failed):
  | Column    | Type   | Description or meaning |
  |-----------|--------|------------------------|
  | MachineId | string | Single-column list of machine IDs considered internal. Exact column name not confirmed; inferred from usage. |
- Column explain:
  - MachineId: the membership key used to set IsInternalUser for both VS Code and CLI populations.

Additional guidance
- Time windows and freshness: Since refresh delay is unknown, prefer conservative time windows (e.g., exclude the most recent 24–48 hours for operational reporting). The query uses LatestFirstDebugTime = now() - 3d to allow a 3-day window for users to complete first debug before labeling as “never success.”
- Version normalization: For sortable versions, convert “a.b.c” to an integer (a*10000 + b*100 + c) or split and left-pad minor for string sorting. This pattern appears throughout and avoids lexicographic traps.
- Anti-patterns:
  - Relying on missing CorrelationId or using 'no-session-id' leads to misgrouped sessions.
  - Mixing client populations (VS/VS Code/CLI) without tagging client types will distort success metrics.
  - Treating transient prerequisite failures (e.g., PrerequisitesValidationError with specific CheckResults) as final failures; the provided logic remaps or excludes certain cases.
- Sharded unions and composition:
  - Union patterns combine client-specific views (e.g., v5Errors/v5SuccessRate with VS results). Keep client tagging (ClientName) and derived ReleaseType clear to avoid misinterpretation.
