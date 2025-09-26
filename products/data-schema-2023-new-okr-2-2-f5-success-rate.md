# 2023 New OKR 2.2: F5 success rate - Product and Data Overview Template

## 1. Product Overview

This schema defines how PMAgent should interpret telemetry and compute the “F5 (local debug) success rate” for TeamsFx across clients. Product scope: 2023 New OKR 2.2: F5 success rate.

- Objective: Measure and report TeamsFx F5 success rate across VS Code (VSC), CLI, and Visual Studio (VS), sliced by version and project type. Normalize session timelines, classify errors, and compute first success to determine if a project is blocked or successful.
- Notes: Timezone assumed UTC unless explicitly adjusted; adopt a 3-day completeness gate from first debug to avoid premature classification.

## 2. Data Platform Overview

- Data Storage: Azure Data Explorer (ADX)
- Product: 2023 New OKR 2.2: F5 success rate
- Product Nick Names:
  - [TODO]Data_Engineer: Fill in commonly used short names or abbreviations (e.g., “F5 Success Rate”, “TeamsFx F5 SR”, “TTK F5”).
- Kusto Cluster: unknown
- Kusto Database: unknown
- Access Control:
  - [TODO]Data_Engineer: If this product’s data has high confidentiality concerns, specify the allowed groups/users. If left blank, general users will be permitted to run analyses on this product, including cross-product scenarios.

-----

# 2023 New OKR 2.2: F5 success rate - Kusto Query Playbook

## Overview
- Product: 2023 New OKR 2.2: F5 success rate
- Summary: Measure and report TeamsFx “F5” (local debug) success rate across clients (VS Code, CLI, Visual Studio), sliced by version and project type. Normalize session timelines, classify errors, and compute “first success” to determine if a project is blocked or successful.
- Cluster: unknown
- Database: unknown

## Conventions & Assumptions

### Time semantics
- Observed timestamp columns:
  - VS Code: ClientTimestamp
  - CLI: eventTimestamp
  - Visual Studio: ClientTimestampUtc
  - Canonical time within aggregated layers: Timestamp (computed via summarize patterns)
- Canonical Time Column: use Timestamp after the aggregation steps; use ClientTimestamp (VSC), eventTimestamp (CLI), ClientTimestampUtc (VS) in raw/event layers.
- Common time windows:
  - A “completeness gate” uses LatestFirstDebugTime = now() - 3d (allow up to 3 days after first debug for users to succeed before classifying as blocked).
- bin usage: not used in provided queries.
- Timezone: unknown (assume timestamps are in UTC for correctness unless explicitly adjusted; ClientTimestampUtc suggests UTC for VS).

### Freshness & Completeness Gates
- Ingestion cadence: unknown.
- Current day completeness: unknown; recommend avoiding same-day data for rate metrics.
- Gate pattern:
  - LatestFirstDebugTime = now() - 3d ensures we only judge projects after they had at least 3 days to succeed.
  - DurationThreshold = 60min (used to cap duration at “infinity” for never-success cases in VS).
- If freshness is uncertain, prefer a last full week/month and avoid evaluating projects whose FirstDebugTime is within the last 3 days.

### Joins & Alignment
- Frequent keys:
  - ProjectId (primary entity across all clients)
  - CorrelationId (session-level grouping within VSC/CLI)
  - ClientName ∈ {'VSC','CLI','VS'}
  - MachineId; ChannelId (VS); ClientVersion
  - Flags: IsInternalUser, IsTestTool
- Join kinds:
  - leftouter: used to bring FirstSuccessTime and FirstDebugTime into session streams; used to attach project type.
  - inner: used when only projects that have project-type mapping are desired.
- Hygiene after joins:
  - Use summarize arg_min/arg_max to pick representative records.
  - Resolve duplicate columns and rename; drop unused columns via project-away.
  - Normalize versions (pad minor) so BI sorting is stable.

### Filters & Idioms
- Version filters:
  - VSC: ExtensionName == 'ms-teams-vscode-extension', ExtensionVersion in v5Versions
  - CLI: cliversion in v5Versions and cliversion matches regex '\d+\.\d+\.\d+$'
  - VS: ExeVersion !in v5Versions and only versions ≥ 17.6
- Excluding V4:
  - Projects created in V4 are derived (distinct ProjectId where ExtensionVersion startswith '4.') and excluded downstream.
- Error normalization:
  - Special-case ‘Ext.PrerequisitesValidationError’ using CheckResults to remap error codes (e.g., ports occupancy → PortsConflictError; M365 account → specific error codes).
- Internal/Test data:
  - IsInternalUser via InternalMachineIds (VSC/CLI) or VS login flag ('true') for VS.
  - IsTestTool via known env IDs from Properties['env.teamsfx_env'].
- Manifest/metadata signals:
  - Metadata event counts and properties used to detect project characteristics.

### Cross-cluster/DB & Sharding
- Source qualification: unknown cluster/database; assume tables are in the same ADX database.
- Sharded union patterns:
  - union used to merge client-specific layers (e.g., VSCv5AllValidSessions ∪ CLIv5AllValidSessions; VS debug streams union).

### Table classes
- Facts (event streams):
  - teamsfx_all (VSC events), teamsfx_all_cli (CLI events), teamsfx_all_vs (VS events)
- Dimensions/snapshots:
  - v5ProjectType (project capability mapping to ProjectType)
  - v5Versions (allowed/GA versions for filtering)
  - InternalMachineIds (allowlist for internal users)
- Usage rules:
  - Use facts for measuring sessions and durations.
  - Use dimensions to enrich with project type and filter valid versions.
  - Avoid mixing snapshots with raw facts without time alignment; attach dimension attributes at evaluation time.

### Important Mapping
- AppType (Capabilities) → ProjectType:
  - Bot, Tab, ME (Message Extension), Copilot, else Unknown (regex-based mapping on tolower(AppType))
- ErrorType normalization:
  - If ErrorType == 'user' and ErrorCode in UserErrorCodeShouldBeSystemType, then set ErrorType = 'system'
- ReleaseType:
  - VS: derived from ChannelId contains_cs 'Release'/'Preview'/'IntPreview'
  - VSC/CLI: prerelease detected by regex on ClientVersion with long patch (>=3 digits)

## Entity & Counting Rules (Core Definitions)
- Entity model:
  - ProjectId → primary entity
  - Sessions aggregated by CorrelationId (VSC/CLI), and by ordered event pairs (VS)
  - Grouping levels: by ProjectId, ClientName, ClientVersion, ProjectType, MachineId, ChannelId (VS)
- Definitions:
  - F5 success (VSC):
    - debug-all event IsSuccess == true
  - F5 success (CLI):
    - preview event IsSuccess == true
  - F5 success (VS):
    - command pair for 'DebugProject' where the success line (EventName == 'vs/teamsfx/command') is present after a start
  - FirstSuccessTime:
    - min(Timestamp) where success is observed (client-specific logic)
  - Blocked / Never Success:
    - IsNeverSuccess := isempty(FirstSuccessTime)
    - Only evaluate sessions up to FirstSuccessTime (or all if never success)
  - DurationBeforeSuccess (VS):
    - sum(Duration) capped at DurationThreshold when IsNeverSuccess

## Views (Reusable Layers)

- UserErrorCodeShouldBeSystemType
  - Purpose: Map certain “user” error codes to “system” category.
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
  - Downstream: applied in v5ProjectData to adjust ErrorType.

- VSCv5AllValidSessions (VSC)
  - Purpose: Build canonical session records per CorrelationId for VSC v5.
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
    | where Name in ('debug-all','debug-prerequisites','metadata','lifecycle-execution')
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
        TestToolCount = countif(Properties['env.teamsfx_env'] in ('f3cc87f...','c585cf...'))
        by CorrelationId
    | where DebugAllCount > 0
    | where not(not(DebugSuccess) and ErrorCode == 'Ext.PrerequisitesValidationError' and CheckResults['Node.js'].result == 'failed')
    | extend IsSuccess = DebugSuccess, IsTestTool = TestToolCount > 0
    | extend ErrorCode = tostring(case(
        ErrorCode != 'Ext.PrerequisitesValidationError', ErrorCode,
        CheckResults['ports occupancy'].result == 'failed', strcat_delim('.', CheckResults['ports occupancy'].source, 'PortsConflictError'),
        CheckResults['Microsoft 365 Account'].result == 'failed', strcat_delim('.', CheckResults['Microsoft 365 Account'].source, CheckResults['Microsoft 365 Account'].errorCode),
        ErrorCode))
    | extend IsInternalUser = MachineId in (InternalMachineIds) 
    | project-away DebugAllCount, TestToolCount
    | extend ClientName = 'VSC';
    ```
  - Downstream: union with CLI; feeds first success/debug derivations.

- CLIv5AllValidSessions (CLI)
  - Purpose: Canonical session records for CLI v5.
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
    | where Name in ('preview','preview-prerequisites','metadata','lifecycle-execution')
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
  - Downstream: union with VSC; feeds first success/debug derivations.

- V5AllProjectType
  - Purpose: Merge project creation-derivation with capabilities to produce ProjectType.
  - Query:
    ```kusto
    let VSCV5TemplateAndSample = teamsfx_all
    | extend Name = tostring(split(EventName, '/')[1])
    | where ExtensionName == 'ms-teams-vscode-extension' and ExtensionVersion in (v5Versions)
      and Name in ('create-project','download-sample')
    | extend ProjectId = tostring(Properties['new-project-id'])
    | summarize (_, ClientVersion) = arg_min(ClientTimestamp, ExtensionVersion) by ProjectId, ExtensionVersion
    | extend ClientName = 'VSC'
    | project ProjectId, ClientVersion, ClientName;

    let CLIV5TemplateAndSample = teamsfx_all_cli
    | where cliversion in (v5Versions) and cliversion matches regex @'\d+\.\d+\.\d+$'
    | extend Name = tostring(split(name, '/')[1])
    | where Name in ('create-project','download-sample')
    | extend ProjectId = tostring(properties['new-project-id'])
    | summarize (_, ClientVersion) = arg_min(eventTimestamp, cliversion) by ProjectId, cliversion
    | extend ClientName = 'CLI'
    | project ProjectId, ClientVersion, ClientName;

    let V5AllTemplateAndSample = VSCV5TemplateAndSample | union CLIV5TemplateAndSample;

    let V5ProjectTypes = v5ProjectType
    | where Capabilities != ''
    | project ProjectId, AppType=tostring(Capabilities);

    let V5AllProjectType = V5AllTemplateAndSample
    | join kind = inner V5ProjectTypes on ProjectId
    | summarize by ProjectId, AppType, ClientVersion
    | extend LowerAppType = tolower(AppType)
    | extend ProjectType = tostring(case(
        LowerAppType matches regex @'\b(bot|adaptive-card|notification|botandmessageextension|tabnonssoandbot)\b', 'Bot',
        LowerAppType matches regex @'\b(tab|dashboard|todo-list|sso-launch-page|hello-world-in-meeting|graph-toolkit|graph-connector-app|live-share-dice-roller|outlook-add-in-set-signature|share-now|intelligent-data-chart-generator)\b', 'Tab',
        LowerAppType matches regex @'\b(message-extension|messageextension|msgext|search-app|link-unfurling|npm-search-connector-m365)\b', 'ME',
        LowerAppType matches regex @'\b(copilot|api-plugin|declarative-agent)\b', 'Copilot',
        'Unknown'))
    | project ProjectId, ProjectType, ClientVersion;
    ```
  - Downstream: used to enrich sessions with ProjectType.

- v5AllValidSessions
  - Purpose: Merge VSC/CLI session streams into a single layer.
  - Query:
    ```kusto
    let v5AllValidSessions = VSCv5AllValidSessions | union CLIv5AllValidSessions;
    ```

- ProjectFirstDebugSessions
  - Purpose: First time a project enters debug (any client).
  - Query:
    ```kusto
    let ProjectFirstDebugSessions = v5AllValidSessions
    | summarize FirstDebugTime = min(Timestamp) by ProjectId, IsTestTool;
    ```

- ProjectFirstSuccessSessions
  - Purpose: First successful debug (client-specific).
  - Query:
    ```kusto
    let ProjectFirstSuccessSessions = v5AllValidSessions
    | where DebugSuccess
    | summarize FirstSuccessTime = min(Timestamp) by ProjectId, ClientName, IsTestTool;
    ```

- v5AllBeforeFirstSuccessSessions
  - Purpose: Evaluate only sessions up to first success or all if never succeeded; exclude V4 projects.
  - Query:
    ```kusto
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

- v5ProjectData
  - Purpose: Final canonical per-project record for VSC/CLI with normalized version and error type.
  - Query:
    ```kusto
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
    ```

- VSDataClean (VS)
  - Purpose: Clean and deduplicate VS events; normalize version and component signals.
  - Query:
    ```kusto
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
        Component = iff(Properties['vs.teamsfx.core.component'] == 'fx-resource-dotnet','fx-resource-frontend-hosting', tostring(Properties['vs.teamsfx.core.component'])),
        ErrorMessage = tostring(Properties['reserved.datamodel.fault.description']),
        IsManifestEvent = EventName == 'vs/teamsfx/core' and Properties['vs.teamsfx.core.event'] == 'metadata' and isnotempty(Properties['vs.teamsfx.core.manifest.id'])
    | where isnotempty(ProjectId)
    | distinct ClientTimestampUtc, CoreEvent, CorrelationId, Component, EventName, EventId, ExeVersion, MacAddressHash, IsInternalUser, Name, NewProjectId, ProjectId, ErrorMessage, ChannelId, IsManifestMetadata
    | extend MachineId = MacAddressHash
    | extend VersionMajor = tostring(split(ExeVersion, '.')[0]), VersionMinor = tostring(split(ExeVersion, '.')[1])
    | extend VersionMinor = iif(toint(VersionMinor) < 10, strcat('0', VersionMinor), VersionMinor)
    | extend VersionMajorMinor = strcat(VersionMajor, '.', VersionMinor);
    ```

- VSDebugProjectEvents and VSPrepareDebugEvents
  - Purpose: Pair start/success events to compute per-command durations.
  - Query:
    ```kusto
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
    ```

- VSAllBeforeFirstSuccessEvents and VSResult
  - Purpose: Aggregate durations until first success; produce final VS success/error records.
  - Query:
    ```kusto
    let TimestampInfinity = datetime(2100, 1, 1);

    let VSAllDebugEvents = VSDebugProjectEvents | union VSPrepareDebugEvents;

    let VSProjectFirstSuccessSessions = VSDebugProjectEvents
    | summarize 
        (FirstSuccessTime, FirstSuccessExeVersion) = arg_min(iff(IsSuccess, ClientTimestampUtc, TimestampInfinity+1d), ExeVersion),
        LastDebugTime = max(ClientTimestampUtc)
        by ProjectId
    | extend FirstSuccessTime = iff(FirstSuccessTime > TimestampInfinity, datetime(null), FirstSuccessTime);

    let VSAllBeforeFirstSuccessEvents = VSAllDebugEvents
    | join kind=leftouter v5ProjectType on ProjectId
    | extend ProjectType = tostring(case(
        Capabilities matches regex @'\b(bot|adaptive-card|notification|botandmessageextension|tabnonssoandbot)\b', 'Bot',
        Capabilities matches regex @'\b(tab|dashboard|todo-list|sso-launch-page|hello-world-in-meeting|graph-toolkit|graph-connector-app|live-share-dice-roller|outlook-add-in-set-signature|share-now|intelligent-data-chart-generator)\b', 'Tab',
        Capabilities matches regex @'\b(message-extension|messageextension|msgext|search-app|link-unfurling|npm-search-connector-m365)\b', 'ME',
        Capabilities matches regex @'\b(copilot|api-plugin|declarative-agent)\b', 'Copilot',
        'Unknown'))
    | join kind=leftouter VSProjectFirstSuccessSessions on ProjectId
    | extend IsNeverSuccess = isempty(FirstSuccessTime)
    | where IsNeverSuccess or ClientTimestampUtc <= FirstSuccessTime;

    let DurationThreshold = 60min;

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

## Query Building Blocks (Copy-paste snippets, contains snippets and description)

- Time window template
  - Description: Apply a conservative evaluation window and gate on first-debug freshness to avoid classifying projects too early.
  - Snippet:
    ```kusto
    // Gate to avoid recent projects being classified before they had time to succeed
    let LatestFirstDebugTime = now() - 3d;
    v5AllValidSessions
    | join kind=leftouter (ProjectFirstDebugSessions) on ProjectId, IsTestTool
    | where FirstDebugTime < LatestFirstDebugTime
    // Optional: also limit to last N days for performance
    | where Timestamp > ago(30d)
    ```

- Join template
  - Description: Standard joins on ProjectId; attach project type and first success with leftouter, then filter by time.
  - Snippet:
    ```kusto
    v5AllValidSessions
    | join kind=leftouter ProjectFirstSuccessSessions on ProjectId, ClientName, IsTestTool
    | extend IsNeverSuccess = isempty(FirstSuccessTime)
    | where IsNeverSuccess or Timestamp <= FirstSuccessTime
    | join kind=leftouter V5AllProjectType on ProjectId
    | extend ProjectType = iff(isempty(ProjectType), 'Unknown', ProjectType)
    ```

- De-dup pattern
  - Description: Use arg_min/arg_max to pick canonical rows; use distinct to cleanse duplicate raw events.
  - Snippets:
    ```kusto
    // Canonical per-session record
    | summarize (_, ClientVersion) = arg_min(ClientTimestamp, ExtensionVersion) by CorrelationId

    // Latest error and earliest version per project
    | summarize 
        (Timestamp, ErrorCode, ErrorMessage, ErrorType) = arg_max(Timestamp, ErrorCode, ErrorMessage, ErrorType),
        (_, ClientVersion) = arg_min(Timestamp, ClientVersion)
      by ProjectId

    // VS: dedup dirty raw events
    | distinct ClientTimestampUtc, EventName, EventId, ProjectId, ...
    ```

- Important filters
  - Description: Exclude V4 projects; normalize PrerequisitesValidationError; filter valid v5 versions; detect internal/test users.
  - Snippets:
    ```kusto
    // Exclude v4 projects
    | where ProjectId !in (V4Projects)

    // Filter valid v5
    | where ExtensionVersion in (v5Versions) // VSC
    | where cliversion in (v5Versions) and cliversion matches regex @'\d+\.\d+\.\d+$' // CLI

    // Normalize PrerequisitesValidationError by CheckResults
    | extend ErrorCode = tostring(case(
        ErrorCode != 'Ext.PrerequisitesValidationError', ErrorCode,
        CheckResults['ports occupancy'].result == 'failed', strcat_delim('.', CheckResults['ports occupancy'].source, 'PortsConflictError'),
        CheckResults['Microsoft 365 Account'].result == 'failed', strcat_delim('.', CheckResults['Microsoft 365 Account'].source, CheckResults['Microsoft 365 Account'].errorCode),
        ErrorCode))

    // Internal and Test Tool detection
    | extend IsInternalUser = MachineId in (InternalMachineIds)
    | extend IsTestTool = Properties['env.teamsfx_env'] in ('<EnvId1>','<EnvId2>')
    ```

- Important Definitions
  - Description: Key business signals to reuse.
  - Snippets:
    ```kusto
    // F5 success per client
    | extend DebugSuccess = (ClientName == 'VSC' and Name == 'debug-all' and IsSuccess)
                         or (ClientName == 'CLI' and Name == 'preview' and IsSuccess)
    // VS success is derived via paired events in prepared views

    // IsNeverSuccess after first success join
    | extend IsNeverSuccess = isempty(FirstSuccessTime)

    // ReleaseType mapping
    | extend ReleaseType = 
        iff(ClientName == 'VS', 
            iff(ChannelId contains_cs 'Release', 'Stable',
                iff(ChannelId contains_cs 'Preview', 'Preview', 'IntPreview')),
            iff(ClientVersion matches regex '\\d+\\.\\d+\\.\\d{3,10}', 'Prerelease', 'Stable'))
    ```

- ID parsing/derivation
  - Description: Extract name, project IDs, correlation IDs, and version normalization.
  - Snippets:
    ```kusto
    // Extract event name component
    | extend Name = tostring(split(EventName, '/')[1])

    // Project ID extraction
    | extend ProjectId = tostring(Properties['project-id']) // VSC
    | extend ProjectId = tostring(properties['project-id']) // CLI
    | extend ProjectId = tostring(Properties['vs.teamsfx.core.project-id']) // VS

    // Version padding for BI sorting
    | extend ClientVersionArr = split(ClientVersion, '.')
    | extend VersionMinor = iif(toint(ClientVersionArr[1]) < 10, strcat('0', ClientVersionArr[1]), ClientVersionArr[1])
    ```

- Sharded union
  - Description: Merge client streams with consistent schema and normalize before summarize.
  - Snippet:
    ```kusto
    let v5AllValidSessions = VSCv5AllValidSessions | union CLIv5AllValidSessions;
    // Align column names/types before union; set ClientName per source.
    ```

## Example Queries (with explanations)

1) VSC v5 Sessions Canonicalization
```kusto
let VSCv5AllValidSessions = teamsfx_all
| extend VersionArr = split(ExtensionVersion, '.')
| extend Version = toint(VersionArr[0])*10000 + toint(VersionArr[1])*100 + toint(VersionArr[2])
| where ExtensionName == 'ms-teams-vscode-extension' and ExtensionVersion in (v5Versions)
| extend Name = tostring(split(EventName, '/')[1]),
        ProjectId = tostring(Properties['project-id']),
        Duration = todouble(Measures['duration']) * 1s,
        IsSuccess = Properties['success'] == 'yes',
        CheckResults = parse_json(tostring(Properties['debug-check-results-safe'])),
        CorrelationId = tostring(Properties['correlation-id'])
| where isnotempty(CorrelationId) and CorrelationId != 'no-session-id'
| where Name in ('debug-all','debug-prerequisites','metadata','lifecycle-execution')
| summarize 
    (_, ClientVersion, MachineId) = arg_min(ClientTimestamp, ExtensionVersion, VSCodeMachineId),
    ProjectId = take_any(tostring(Properties['project-id'])),
    Timestamp = minif(ClientTimestamp, Name == 'debug-all'),
    Duration = take_anyif(todouble(Measures['duration']) * 1s, Name == 'debug-all'),
    DebugSuccess = maxif(IsSuccess, Name == 'debug-all'),
    ErrorCode = take_anyif(tostring(Properties['error-code']), Name == 'debug-all'),
    ErrorMessage = take_anyif(tostring(Properties['error-message']), Name == 'debug-all'),
    ErrorType = take_anyif(tostring(Properties['error-type']), Name == 'debug-all'),
    MetadataCount = countif(Name == 'metadata'),
    TestToolCount = countif(Properties['env.teamsfx_env'] in ('f3cc87...','c585cf...'))
  by CorrelationId
| where DebugAllCount > 0
| where not(not(DebugSuccess) and ErrorCode == 'Ext.PrerequisitesValidationError' and CheckResults['Node.js'].result == 'failed')
| extend IsSuccess = DebugSuccess, IsTestTool = TestToolCount > 0
| extend IsInternalUser = MachineId in (InternalMachineIds)
| project-away DebugAllCount, TestToolCount
| extend ClientName = 'VSC';
```
- Description: Converts raw VS Code events into one record per CorrelationId with key signals (Timestamp, IsSuccess, Error details). Filters valid versions and remaps certain prerequisite errors. Adapt by adjusting version filters and adding additional Name events if needed.

2) CLI v5 Sessions Canonicalization
```kusto
let CLIv5AllValidSessions = teamsfx_all_cli
| extend VersionArr = split(cliversion, '.')
| extend Version = toint(VersionArr[0])*10000 + toint(VersionArr[1])*100 + toint(VersionArr[2])
| where cliversion in (v5Versions) and cliversion matches regex @'\d+\.\d+\.\d+$'
| extend Name = tostring(split(name, '/')[1]),
        ProjectId = tostring(properties['project-id']),
        Duration = todouble(measures['duration']) * 1s,
        IsSuccess = properties['success'] == 'yes',
        CorrelationId = tostring(properties['correlation-id'])
| where isnotempty(CorrelationId) and CorrelationId != 'no-session-id'
| where Name in ('preview','preview-prerequisites','metadata','lifecycle-execution')
| summarize 
    (_, ClientVersion, MachineId) = arg_min(eventTimestamp, cliversion, machineid),
    ProjectId = take_any(tostring(properties['project-id'])),
    Timestamp = minif(eventTimestamp, Name == 'preview'),
    Duration = take_anyif(todouble(measures['duration']) * 1s, Name == 'preview'),
    DebugSuccess = maxif(IsSuccess, Name == 'preview'),
    ErrorCode = take_anyif(tostring(properties['error-code']), Name == 'preview'),
    ErrorMessage = take_anyif(tostring(properties['error-message']), Name == 'preview'),
    ErrorType = take_anyif(tostring(properties['error-type']), Name == 'preview')
  by CorrelationId
| where DebugAllCount > 0
| where not(not(DebugSuccess) and ErrorCode == 'Ext.PrerequisitesValidationError')
| extend IsSuccess = DebugSuccess
| extend IsInternalUser = MachineId in (InternalMachineIds)
| project-away DebugAllCount
| extend ClientName = 'CLI';
```
- Description: Mirrors the VSC session canonicalization for CLI. Enforces version regex to filter malformed versions. Adapt by changing Name filters or adding platform-based exclusions.

3) Project Type Mapping
```kusto
let V5ProjectTypes = v5ProjectType
| where Capabilities != ''
| project ProjectId, AppType=tostring(Capabilities);

let V5AllProjectType = V5ProjectTypes
| extend LowerAppType = tolower(AppType)
| extend ProjectType = tostring(case(
    LowerAppType matches regex @'\b(bot|adaptive-card|notification|botandmessageextension|tabnonssoandbot)\b', 'Bot',
    LowerAppType matches regex @'\b(tab|dashboard|todo-list|sso-launch-page|hello-world-in-meeting|graph-toolkit|graph-connector-app|live-share-dice-roller|outlook-add-in-set-signature|share-now|intelligent-data-chart-generator)\b', 'Tab',
    LowerAppType matches regex @'\b(message-extension|messageextension|msgext|search-app|link-unfurling|npm-search-connector-m365)\b', 'ME',
    LowerAppType matches regex @'\b(copilot|api-plugin|declarative-agent)\b', 'Copilot',
    'Unknown'))
| project ProjectId, ProjectType;
```
- Description: Normalizes raw capabilities to coarse ProjectType categories. Adapt by adding new regex branches as capabilities expand (e.g., Outlook Add-in).

4) First Success and Before-First-Success Filter
```kusto
let LatestFirstDebugTime = now() - 3d;

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
| where FirstDebugTime < LatestFirstDebugTime;
```
- Description: Enforces evaluation up to first success and the 3-day gate from first debug to avoid premature classification. Adapt by changing 3d if business policy changes.

5) Visual Studio Debug Duration Pairing
```kusto
let VSDebugProjectEvents = VSDataClean
| where Name == 'DebugProject'
| order by ClientTimestampUtc asc
| serialize
| extend StartTime = iff(prev(ProjectId, 1) == ProjectId 
                      and prev(EventName, 1) == 'vs/teamsfx/command/start' 
                      and prev(Name, 1) == 'DebugProject', prev(ClientTimestampUtc, 1), datetime(null))
| extend IsSuccess = EventName == 'vs/teamsfx/command'
| extend Duration = (ClientTimestampUtc - StartTime);
```
- Description: Pairs start/success events to compute deployment durations (DebugProject). Adapt by adding guardrails to drop rows where StartTime is null or Duration is negative.

6) VS Aggregation to Final Signals
```kusto
let TimestampInfinity = datetime(2100, 1, 1);
let DurationThreshold = 60min;

let VSProjectFirstSuccessSessions = VSDebugProjectEvents
| summarize 
    (FirstSuccessTime, FirstSuccessExeVersion) = arg_min(iff(IsSuccess, ClientTimestampUtc, TimestampInfinity+1d), ExeVersion),
    LastDebugTime = max(ClientTimestampUtc)
    by ProjectId
| extend FirstSuccessTime = iff(FirstSuccessTime > TimestampInfinity, datetime(null), FirstSuccessTime);

let VSAllBeforeFirstSuccessEvents = (VSDebugProjectEvents | union VSPrepareDebugEvents)
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
    (LastEventTime, LastErrorMessage, MachineId, IsInternalUser) = arg_max(ClientTimestampUtc, ErrorMessage, MachineId, IsInternalUser)
    by ProjectId, VersionMajorMinor, ChannelId
| extend DurationBeforeSuccess = iff(IsNeverSuccess, DurationThreshold, Duration)
| extend Timestamp = LastEventTime
| extend ErrorType = iif(IsNeverSuccess, 'system', '');
```
- Description: Computes first success, accumulates durations up to that point, and builds final VS-level signals. Adapt by adding per-channel filtering or project-type joins for slicing.

7) Merge VS + VSC/CLI and ReleaseType Derivation
```kusto
union 
  (v5ProjectData | extend Tag = 'error' | where IsNeverSuccess),
  (v5ProjectData | extend Tag = 'SuccessRate'),
  (VSResult | project ClientName = 'VS', ClientVersion = VersionMajorMinor, ProjectId, MachineId, IsInternalUser, ErrorMessage = LastErrorMessage, ErrorCode = substring(LastErrorMessage, 0, 50), Tag = 'error', ChannelId, ProjectType, Timestamp, ErrorType | where IsNeverSuccess),
  (VSResult | project ClientName = 'VS', ClientVersion = VersionMajorMinor, ProjectId, MachineId, IsInternalUser, Tag = 'SuccessRate', IsNeverSuccess, ChannelId, ProjectType, Timestamp, ErrorType)
| extend ReleaseType = 
    iff(ClientName == 'VS', 
        iff(ChannelId contains_cs 'Release', 'Stable',
            iff(ChannelId contains_cs 'Preview', 'Preview', 'IntPreview')),
        iff(ClientVersion matches regex '\\d+\\.\\d+\\.\\d{3,10}', 'Prerelease', 'Stable'))
| extend IsTestTool = iff(isempty(IsTestTool), false, IsTestTool)
```
- Description: Produces unified output for BI across all clients, adding ReleaseType and IsTestTool defaults. Adapt by filtering cohorts (e.g., only Stable) or adding more classification rules.

8) Excluding V4 Projects
```kusto
let V4Projects = teamsfx_all
| where ExtensionVersion startswith '4.'
| extend ProjectId = tostring(Properties['project-id'])
| distinct ProjectId;

... 
| where ProjectId !in (V4Projects)
```
- Description: Identifies V4-origin projects and excludes them from v5 analysis. Adapt by toggling this exclusion depending on migration stage.

## Reasoning Notes (only if uncertain)
- Cluster/database: unknown; we assume single ADX database with these tables.
- Timezone: ClientTimestampUtc suggests UTC for VS; VSC/CLI timestamps assumed UTC but not explicitly stated.
- Success definition: We adopt client-specific success events (debug-all, preview, VS command) directly from queries; alternatives could count any positive outcome events.
- Error normalization: Special-case mapping for Ext.PrerequisitesValidationError based on CheckResults; this assumes consistent schema.
- Internal users: VSC/CLI use InternalMachineIds; VS uses login flag—if these lists are incomplete, internal detection may be noisy.
- Test tool detection: Based on env IDs; there may be additional test environments not listed; we keep two IDs as canonical.
- 3-day gate: Chosen to avoid premature classification; if ingestion is delayed or users take longer, consider 7-day gate.
- Version filtering: v5Versions dimension used; if it contains pre-release entries, consider additional filters (e.g., exclude prerelease).
- VS dedup: distinct is used to sanitize dirty data; if duplication exists beyond selected columns, further dedup keys may be needed.
- ReleaseType inference: For VSC/CLI, prerelease detection uses a regex on patch digits; alternative is an explicit version list from v5Versions with a flag.

## Canonical Tables

This playbook summarizes how the product’s Kusto queries use the core telemetry tables (by version and project type) to compute “2023 New OKR 2.2: F5 success rate.” All tables below are in the product’s configured database: vscode-ext-aggregate. Cluster host is unknown.

Order reflects how the provided queries reference them. Priority is Normal for all.

### Table name: teamsfx_all (database: vscode-ext-aggregate)
- Priority: Normal
- What this table represents: VS Code extension telemetry events for ms-teams-vscode-extension. Each row is an event with measures and properties collected from the extension session.
- Freshness expectations: Unknown. The table contains IngestionTime per row. The queries use now() - 3d to define a “LatestFirstDebugTime” window; be cautious when analyzing current-day data.
- When to use / When to avoid:
  - Use to compute VS Code F5 “debug-all” success, prerequisites, lifecycle, and metadata.
  - Use to derive project-level signals by CorrelationId (group events per session).
  - Use to filter v5 client versions via v5Versions.
  - Avoid mixing with CLI or VS telemetry; choose the matching table (teamsfx_all_cli, teamsfx_all_vs).
- Similar tables & how to choose:
  - teamsfx_all_cli: CLI events (name/cliversion schema). Use for CLI workflows (“preview”).
  - teamsfx_all_vs: Visual Studio telemetry (ExeVersion, ChannelId schema). Use for VS workflows (DebugProject/Debug).
- Common Filters:
  - ExtensionName == 'ms-teams-vscode-extension'
  - ExtensionVersion in (v5Versions)
  - EventName suffix in {debug-all, debug-prerequisites, metadata, lifecycle-execution}
  - CorrelationId not empty and != 'no-session-id'
  - Exclude v4 projects via ExtensionVersion startswith '4.'
  - Identify internal users by VSCodeMachineId in (InternalMachineIds)

- Table columns:

| Column | Type | Description or meaning |
|-----------------|----------|------------------------|
| EventName | string | Event name (e.g., ‘ms-teams-vscode-extension/debug-all’, used to split Name). |
| Attributes | dynamic | Additional attributes payload; not used directly in the provided queries. |
| ClientTimestamp | datetime | Client-side event timestamp; used to compute session timing/summarize (e.g., minif for debug-all). |
| DataHandlingTags | string | Data handling labels; not used directly in the provided queries. |
| ExtensionName | string | VS Code extension ID; filter equals 'ms-teams-vscode-extension'. |
| ExtensionVersion | string | VS Code extension version string; filtered against v5Versions and used to make sortable ClientVersion. |
| GeoCity | string | Geo city; not used in provided queries. |
| GeoCountryRegionIso | string | Geo country/region; not used in provided queries. |
| Measures | dynamic | Numeric measures; measures['duration'] used to compute Duration for debug-all. |
| NovaProperties | dynamic | Additional properties; not used in provided queries. |
| Platform | string | Platform OS; collected via take_any in VSC v5 sessions. |
| PlatformVersion | string | Platform version; not used directly. |
| Properties | dynamic | Core event properties; keys accessed include 'project-id', 'success', 'correlation-id', 'debug-check-results-safe', 'error-code', 'error-message', 'error-type', 'debug-last-event-name', 'debug-task-args', 'debug-prelaunch-task-info', 'lifecycle'. |
| ServerTimestamp | datetime | Server-side ingestion time; not used directly. |
| Tags | dynamic | Additional tagging; not used directly. |
| VSCodeMachineId | string | Machine ID; used to identify internal users via InternalMachineIds. |
| VSCodeSessionId | string | VS Code session ID; not used directly. |
| VSCodeVersion | string | VS Code version; not used directly. |
| WorkloadTags | string | Workload tags; not used directly. |
| LanguageServerVersion | string | Language server version; not used. |
| IngestionTime | datetime | ADX ingestion time; indicates freshness. |
| SchemaVersion | string | Schema version; not used. |
| Method | string | Event method; not used. |
| Duration | real | Event duration; rarely used in favor of Measures['duration']. |
| SQMMachineId | string | Machine ID from SQM; not used. |
| DevDeviceId | string | Dev device ID; not used. |
| IsInternal | bool | Internal flag; not used directly (queries use VSCodeMachineId mapping). |
| ABExpAssignmentContext | string | A/B flight info; not used. |
| Source | string | Source identifier; not used. |
| SKU | string | SKU; not used. |
| Model | string | Model; not used. |
| RequestId | string | Request ID; not used. |
| ConversationId | string | Conversation ID; not used. |
| ResponseType | string | Response type; not used. |
| ToolName | string | Tool name; not used. |
| Outcome | string | Outcome; not used. |
| IsEntireFile | string | Entire file flag; not used. |
| ToolCounts | string | Tool counts; not used. |
| Isbyok | int | BYOK flag; not used. |
| TimeToFirstToken | int | Latency metric; not used. |
| TimeToComplete | int | Completion latency; not used. |
| TimeDelayms | int | Delay ms; not used. |
| SurvivalRateFourgram | real | Model metric; not used. |
| TokenCount | real | Token count; not used. |
| PromptTokenCount | real | Prompt token count; not used. |
| NumRequests | int | Number of requests; not used. |
| Turn | int | Conversation turn; not used. |
| ResponseTokenCount | real | Response token count; not used. |
| TotalNewDiagnostics | int | Diagnostics count; not used. |
| Rounds | real | Rounds; not used. |
| AvgChunkSize | real | Avg chunk size; not used. |
| Command | string | Command name; not used. |
| CopilotTrackingId | string | Tracking ID; not used. |
| IntentId | string | Intent ID; not used. |
| Participant | string | Participant; not used. |
| ToolGroupState | string | Tool group state; not used. |
| DurationMS | long | Duration in ms; not used in queries provided. |

- Column Explain:
  - ExtensionName, ExtensionVersion: Filter to 'ms-teams-vscode-extension' and v5 versions; critical for version-scoped analysis.
  - EventName: Parsed to Name with split(EventName, '/')[1] to isolate debug-all, debug-prerequisites, metadata, lifecycle-execution.
  - Properties: Central store for success flags, correlation id, project id, error fields, and check results JSON.
  - Measures['duration']: Used to compute debug-all Duration.
  - ClientTimestamp: Drives session ordering and min/max aggregations.
  - VSCodeMachineId: Used with InternalMachineIds to flag internal usage.
  - Platform: Captured as context in summaries.

---

### Table name: teamsfx_all_cli (database: vscode-ext-aggregate)
- Priority: Normal
- What this table represents: Teams Toolkit CLI telemetry events. Each row is a CLI event with name, cliversion, properties, and measures.
- Freshness expectations: Unknown. IngestionTime present. Queries filter cliversion via v5Versions and regex for version format.
- When to use / When to avoid:
  - Use to evaluate CLI “preview”, prerequisites, metadata, lifecycle events.
  - Use to compute Duration and success via measures/properties.
  - Avoid for VS Code or Visual Studio workflows; use teamsfx_all or teamsfx_all_vs respectively.
- Similar tables & how to choose:
  - teamsfx_all: VS Code extension events.
  - teamsfx_all_vs: Visual Studio events.
- Common Filters:
  - cliversion in (v5Versions) and matches regex '\d+\.\d+\.\d+$'
  - Name in {preview, preview-prerequisites, metadata, lifecycle-execution}
  - properties['correlation-id'] not empty and != 'no-session-id'
  - properties['success'] == 'yes' for success signals
  - Internal user via machineid in (InternalMachineIds)

- Table columns:

| Column | Type | Description or meaning |
|-----------------|----------|------------------------|
| eventTimestamp | datetime | Client-side event timestamp for CLI events; used to compute Timestamp and ordering. |
| name | string | Event name (e.g., 'cli/preview'); split(name, '/')[1] to extract action. |
| properties | dynamic | Event properties; keys used include 'project-id', 'new-project-id', 'success', 'correlation-id', 'error-code', 'error-message', 'error-type', 'manifest.id'. |
| cliversion | string | CLI version; filtered against v5Versions and regex format. |
| machineid | string | Machine identifier; used to flag internal users via InternalMachineIds. |
| os | string | Operating system; not used directly. |
| platformversion | string | Platform version; not used directly. |
| measures | dynamic | Numeric measures; measures['duration'] used to compute preview Duration. |
| operation_Name | string | Operation name; not used. |
| operation_Id | string | Operation ID; not used. |
| operation_ParentId | string | Parent operation ID; not used. |
| session_Id | string | Session ID; not used. |
| user_Id | string | User ID; not used. |
| client_Type | string | Client type; not used. |
| client_Model | string | Client model; not used. |
| client_OS | string | Client OS; not used. |
| client_City | string | Client city; not used. |
| client_StateOrProvince | string | Client state/province; not used. |
| client_CountryOrRegion | string | Client country/region; not used. |
| client_Browser | string | Client browser; not used. |
| itemCount | long | Item count; not used. |
| RecordId | string | Record ID; not used. |
| Tags | dynamic | Tags; not used. |
| DataHandlingTags | string | Data handling; not used. |
| NovaProperties | dynamic | Additional properties; not used. |
| IngestionTime | datetime | ADX ingestion time; indicates freshness. |
| DataHandling | dynamic | Data handling; not used. |
| GdprQuarantined | dynamic | GDPR quarantine flags; not used. |

- Column Explain:
  - cliversion: Version filter source; combined with regex to exclude malformed versions.
  - name: Provides action names “preview”, “preview-prerequisites”, “metadata”, “lifecycle-execution”.
  - properties: Carries success, correlation-id, error fields, and manifest metadata for joins and filters.
  - measures['duration']: Used for Duration metric on preview events.
  - machineid: Used to flag internal usage via InternalMachineIds.
  - eventTimestamp: Drives min/max (Timestamp) aggregations.

---

### Table name: teamsfx_all_vs (database: vscode-ext-aggregate)
- Priority: Normal
- What this table represents: Visual Studio telemetry for Teams Toolkit. Events include channel/version, client timestamps, and rich Properties payload used to derive Teams Toolkit actions (DebugProject, Debug, metadata).
- Freshness expectations: Unknown. IngestionTime present per row. Queries filter VS versions (ExeVersion) and aggregate durations over sequences.
- When to use / When to avoid:
  - Use to calculate F5 deployment (DebugProject) and Prepare Teamsfx environment (Debug) durations and success.
  - Use to compute first successful F5 timestamp and pre-success durations.
  - Avoid for VS Code or Visual Studio workflows; use teamsfx_all or teamsfx_all_cli.
- Similar tables & how to choose:
  - teamsfx_all: VS Code extension events.
  - teamsfx_all_cli: CLI events.
- Common Filters:
  - ExeVersion !in (v5Versions) and VersionMajor >= 17 and VersionMinor >= 6
  - Properties['vs.teamsfx.name'] in {DebugProject, Debug}
  - ProjectId is not empty; dedup distinct rows due to dirty data
  - Use ChannelId to classify ReleaseType: 'Stable', 'Preview', 'IntPreview'

- Table columns:

| Column | Type | Description or meaning |
|-----------------|----------|------------------------|
| EventId | string | Event ID; not used directly. |
| EventName | string | VS telemetry event name (e.g., 'vs/teamsfx/command', 'vs/teamsfx/command/start'); used in Debug/DebugProject pipelines. |
| ABExpFlights | string | A/B experiment flights; not used. |
| ActiveProjectId | string | Active project ID; not used (queries derive ProjectId from Properties). |
| ActivityCorrelationId | string | Activity correlation; not directly used. |
| ActivityDurationInMilliseconds | long | Activity duration; not used. |
| ActivityEndInTicks | long | End ticks; not used. |
| ActivityStartInTicks | long | Start ticks; not used. |
| AdvancedServerTimestampUtc | datetime | Server timestamp; not used directly. |
| AltSecId | string | Alternative security ID; not used. |
| Attributes | dynamic | Attributes payload; not used directly. |
| BranchName | string | Branch name; not used. |
| BuildManifestId | string | Build manifest ID; not used. |
| BuildNumber | real | Build number; not used. |
| BuildNumberFull | real | Build number full; not used. |
| BuildNumberMajorVersion | real | Major build number; not used directly. |
| BuildNumberMicroUpdate | string | Micro update; not used. |
| BuildNumberMinorVersion | real | Minor build number; not used. |
| BuildWorkloads | string | Workloads string; not used. |
| ChannelId | string | VS channel (Release/Preview/IntPreview classification in output). |
| ChannelManifestId | string | Channel manifest; not used. |
| ClientTimestampUtc | datetime | Client-side timestamp; used for ordering, Start/End pairing, duration computations, and first success. |
| ClrVersion | string | CLR version; not used. |
| CommandGuid | string | Command GUID; not used. |
| CommandName | string | Command name; not used directly (Name is derived from Properties). |
| CommandSource | string | Source; not used. |
| ComputerName | string | Computer name; not used. |
| CpuArchitecture | string | CPU architecture; not used. |
| CpuCount | real | CPU count; not used. |
| CpuDataWidth | real | CPU data width; not used. |
| CpuDescription | string | CPU description; not used. |
| CpuFamily | real | CPU family; not used. |
| CpuFrequency | real | CPU frequency; not used. |
| CpuModel | real | CPU model; not used. |
| CpuStepping | real | CPU stepping; not used. |
| DataHandlingTags | string | Data handling; not used. |
| DisplayColorDepth | real | Display color depth; not used. |
| DisplayCount | real | Display count; not used. |
| DisplayDpi | real | DPI; not used. |
| DisplayHighContrastEnabled | bool | High contrast flag; not used. |
| DisplayHighContrastName | string | High contrast name; not used. |
| DisplayResolution | real | Resolution; not used. |
| DisplayScalingFactor | real | Scaling factor; not used. |
| DisplayVirtualXY | string | Virtual XY; not used. |
| DisplayXY | string | Display XY; not used. |
| ExeName | string | Executable name; not used. |
| ExeVersion | string | Visual Studio version; filtered (>= 17.6), used in first-success version output. |
| ExtensionName | string | Extension name; not used directly. |
| Extensions | dynamic | Extensions; not used. |
| ExtensionTypeName | string | Extension type; not used. |
| ExtensionVersion | string | Extension version; not used directly in VS path. |
| FeedbackSessionId | string | Feedback session id; not used. |
| Flags | long | Flags; not used. |
| GeoCity | string | Geo city; not used. |
| GeoCountryRegionIso | string | Geo country; not used. |
| HardDriveFreeVolumeSize | real | Free volume size; not used. |
| HardDriveOsMediaType | string | OS media type; not used. |
| HardDriveProductFileSystemType | string | FS type; not used. |
| HardDriveProductMediaType | string | Media type; not used. |
| HardDriveTotalSize | real | Total size; not used. |
| HardDriveTotalVolumeSize | real | Total volume size; not used. |
| IdentityProvider | string | Identity provider; not used. |
| IdSubject | string | Subject ID; not used. |
| InLowImpactMode | string | Low impact mode; not used. |
| IsInternal | bool | Internal flag; not used directly (IsInternalUser derived from Properties and MachineId). |
| IsOptedIn | bool | Opt-in; not used. |
| LastSolutionBuildId | string | Last solution build id; not used. |
| Locale | string | Locale; not used. |
| LocaleCode | string | Locale code; not used. |
| MacAddressHash | string | MachineId source for VS path; used to derive MachineId (extended in query). |
| MachineId | string | Machine identifier; used in VSResult via arg_max. |
| ManifestId | string | Manifest ID; not used directly (IsManifestEvent derived from Properties). |
| Measures | dynamic | Measures; not used directly (durations computed from timestamps). |
| MicroUpdateVersion | string | Micro update version; not used. |
| NovaProperties | dynamic | Additional properties; not used. |
| OID | string | OID; not used. |
| Os | string | OS; not used. |
| OsLocale | string | OS locale; not used. |
| OsLocaleUser | string | User locale; not used. |
| OsLocaleUserUi | string | User UI locale; not used. |
| OsMajorVersion | real | OS major; not used. |
| OsMinorVersion | real | OS minor; not used. |
| OsServicePack | real | Service pack; not used. |
| OsVersion | string | OS version; not used. |
| PackageGuid | string | Package GUID; not used. |
| PersonalizationVsId | string | Personalization VS ID; not used. |
| Product | string | Product name; not used. |
| ProjectId | string | Project ID; core key for joining to project types and aggregation. |
| Properties | dynamic | Core event properties used to derive Name, correlation id, project id, component, error message, vs teamsfx events. |
| PUID | string | PUID; not used. |
| RamTotal | real | RAM; not used. |
| SequenceNumber | int | Sequence number; not used. |
| SessionId | string | Session ID; not used. |
| Sku | string | SKU; not used. |
| SkuId | real | SKU ID; not used. |
| SolutionId | string | Solution ID; not used. |
| SolutionSessionId | string | Solution session ID; not used. |
| Tags | dynamic | Tags; not used. |
| TelemetryApiVersion | string | Telemetry API version; not used. |
| TelemetryChannelUsed | string | Channel used; not used. |
| TimeSinceSessionStart | long | Time since session start; not used. |
| UserAlias | string | User alias; not used. |
| UserDomainName | string | Domain; not used. |
| UserId | string | User ID; not used. |
| UtcDeviceClass | string | Device class; not used. |
| UtcDeviceLocalId | string | Local device id; not used. |
| UtcFlags | string | UTC flags; not used. |
| UtcGlobalDeviceId | string | Global device id; not used. |
| VirtualMachineAzureImage | string | VM image; not used. |
| VsId | string | VS ID; not used. |
| VsInstanceId | string | VS instance id; not used. |
| VsLocale | string | VS locale; not used. |
| WorkloadTags | string | Workload tags; not used. |
| SessionRole | string | Session role; not used. |
| ConnectedSessionId | string | Connected session id; not used. |
| RemoteSessionIds | dynamic | Remote session ids; not used. |
| CloudEnvironmentId | string | Cloud environment; not used. |
| IsAzureCloudEnvironment | bool | Azure cloud env flag; not used. |
| RemoteRepoURLInternal | string | Remote repo internal URL; not used. |
| DataModelActionType | string | Data model action; not used. |
| DataModelCorrelationId | string | Data model correlation id; not used. |
| DataModelActionResult | string | Data model result; not used. |
| VsCoreIs64BitProcess | bool | 64-bit process; not used. |
| IngestionTime | datetime | ADX ingestion time; indicates freshness. |
| ProcessArchitecture | string | Process arch; not used. |
| SchemaVersion | string | Schema version; not used. |
| SolutionId1 | string | Alternative solution id; not used. |
| MachineId1 | string | Alternative machine id; not used. |
| IsDevBox | bool | DevBox flag; not used. |
| DevDeviceId | string | Dev device id; not used. |

- Column Explain:
  - ClientTimestampUtc: Essential for ordering, pairing start/command events, and computing Duration for DebugProject/Debug.
  - EventName: Used to identify 'vs/teamsfx/command/start' vs 'vs/teamsfx/command' for success and duration pairs.
  - ExeVersion: Version gating (>= 17.6) and first-success version summarization.
  - ChannelId: Used post-aggregation to classify ReleaseType: Stable/Preview/IntPreview.
  - Properties: Source for vs.teamsfx fields: name, core.correlation-id, core.project-id, component, reserved.datamodel.fault.description (error message), manifest.id.
  - MacAddressHash: Extended to MachineId in the pipeline; used for internal user flag and downstream joins.
  - ProjectId: Key for summarization, join to v5ProjectType, first success, and final outputs.

---

### Table name: v5ProjectType (database: vscode-ext-aggregate)
- Priority: Normal
- What this table represents: Reference mapping of ProjectId to capability labels and boolean flags describing whether the project is a Tab, Bot, Compose Extension, and Extension.
- Freshness expectations: Unknown. Used as a static/joinable dimension in the queries.
- When to use / When to avoid:
  - Use to classify project types for VS (VSAllBeforeFirstSuccessEvents) and VS Code/CLI (via V5ProjectTypes/V5AllProjectType view).
  - Avoid inferring types directly from event names; rely on this table for authoritative classification.
- Similar tables & how to choose:
  - No alternative source in input; views V5ProjectTypes and V5AllProjectType use this table.
- Common Filters:
  - where Capabilities != '' to ensure valid classification
  - joins on ProjectId

- Table columns:

| Column | Type | Description or meaning |
|-----------------|----------|------------------------|
| ProjectId | string | Unique project identifier used in joins. |
| isTab | bool | Flag if project has Tab capability. |
| isBot | bool | Flag if project has Bot capability. |
| isComposeExtension | bool | Flag if project has Compose Extension capability. |
| isExtension | bool | Flag if project is an Extension. |
| Capabilities | string | Capability labels used to derive classified ProjectType (Bot/Tab/ME/Copilot). |

- Column Explain:
  - ProjectId: Join key to VS/CLI/VSC sessions.
  - Capabilities: Parsed (regex) to categorize into Bot/Tab/ME/Copilot; forms the ProjectType output.
  - isTab/isBot/isComposeExtension/isExtension: Boolean indicators; may corroborate string Capabilities.

---

### Table name: v5Versions (database: vscode-ext-aggregate)
- Priority: Normal
- What this table represents: Reference list of supported/recognized v5 version identifiers. Used to filter extension/CLI version events.
- Freshness expectations: Unknown. Assumed stable; occasionally updated to add/remove versions.
- When to use / When to avoid:
  - Use in where ExtensionVersion in (v5Versions) and cliversion in (v5Versions).
  - Avoid hardcoding version lists; rely on this table.
- Similar tables & how to choose:
  - No alternative provided. A toscalar(make_set(Version)) pattern is used for VS filtering in queries.
- Common Filters:
  - Inclusion (‘in’) for ExtensionVersion/cliversion
  - Regex validation on CLI side to ensure version format

- Table columns:

| Column | Type | Description or meaning |
|-----------------|----------|------------------------|
| Version | string | Version string (e.g., '5.x.y'); used in ‘in’ predicates and toscalar(make_set(Version)). |

- Column Explain:
  - Version: Feed to ‘in’ filters for VS Code and CLI version gating; prevents including v4 or invalid/pre-release formats.

---

### Table name: InternalMachineIds (database: vscode-ext-aggregate)
- Priority: Normal
- What this table represents: Reference list of MachineId values identifying internal users/devices. Used to flag internal usage across clients.
- Freshness expectations: Unknown. Treated as a static lookup; update cadence not specified.
- When to use / When to avoid:
  - Use in extend IsInternalUser = MachineId in (InternalMachineIds) for VSC/CLI paths.
  - Avoid deriving internal flag from other heuristics; use this lookup for determinism.
- Similar tables & how to choose:
  - No alternative provided.
- Common Filters:
  - ‘in (InternalMachineIds)’ in extend steps

- Table columns:

| Column | Type | Description or meaning |
|-----------------|----------|------------------------|
| MachineId | string | Machine ID to be matched against client machine identifiers for internal flag. |

- Column Explain:
  - MachineId: Single-column set membership for internal-user detection in VSC/CLI paths; VS path uses MacAddressHash extended to MachineId.

---

### Table name: teamsfx_all (V4Projects view context)
- Priority: Normal
- What this table represents: Same as above; additionally used to isolate V4 projects via ExtensionVersion startswith '4.' to exclude from v5 analyses.
- Freshness expectations: Unknown.
- When to use / When to avoid:
  - Use to compute the set of ProjectId created with v4 to exclude from v5 metrics.
  - Avoid for v5-only paths without needing v4 exclusion.
- Similar tables & how to choose:
  - Not applicable; this is a filtered subset (V4Projects view) of teamsfx_all.
- Common Filters:
  - ExtensionVersion startswith '4.'
  - Properties['project-id'] non-empty

- Table columns: See the teamsfx_all column list above (identical).
- Column Explain:
  - ExtensionVersion: Startswith '4.' indicates v4 project creation; yields distinct ProjectId set to exclude.

---

Guidance and assumptions used by the product:
- Version gating: VS Code and CLI paths filter events to v5 versions using v5Versions; CLI additionally validates version format via regex '\d+\.\d+\.\d+$'.
- Session semantics: Events are grouped by CorrelationId for VSC/CLI; debug-all Timestamp/Duration, prerequisites checks, and lifecycle failures are aggregated per session.
- First success logic: First success is computed across all versions; “before first success” includes all events up to the first success (or all if never successful).
- Internal user detection: Per-client MachineId membership in InternalMachineIds indicates internal users; in VS path MachineId is derived from MacAddressHash.
- Error normalization: Specific user-type errors are reclassified to system when ErrorCode is in UserErrorCodeShouldBeSystemType.
- Time-window caution: LatestFirstDebugTime = now() - 3d; users are given 3 days before assuming they are blocked. Freshness/ingestion delays are unknown; be cautious with very recent data.

Conservative defaults for new analyses:
- Use shorter time windows when exploring (e.g., last 7–14 days) and confirm ingestion patterns with IngestionTime.
- Start with top N aggregations per ProjectType and ClientVersion; scale after validation.
- Always filter versions via v5Versions rather than hardcoding strings; validate CLI cliversion format.