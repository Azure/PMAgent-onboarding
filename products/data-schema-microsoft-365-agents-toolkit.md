# Microsoft 365 Agents Toolkit - Product and Data Overview Template

## 1. Product Overview

The Microsoft 365 Agents Toolkit (evolved from Teams Toolkit) helps developers build and deploy agents and apps across Microsoft 365 platforms including Microsoft 365 Copilot, Microsoft Teams, and Microsoft 365. It provides integrated identity, access to cloud storage, Microsoft Graph data, and Azure services with a "zero-configuration" approach, significantly simplifying the development lifecycle.

## 2. Data Platform Overview

- **Data Storage**: Azure Data Explorer (ADX)
- **Product**:
Microsoft 365 Agents Toolkit
- **Product Nick Names**: TeamsFx, M365 Agents Toolkit, ATK, MATK, TTK
- **Kusto Cluster**:
teamsfxaggregation.eastus
- **Kusto Database**:
vscode-ext-aggregate
- **Access Control**: 
  
-----

# Microsoft 365 Agents Toolkit - Kusto Query Playbook

## Overview
- The Microsoft 365 Agents Toolkit, an evolution of Teams Toolkit, is designed to help developers create and deploy agents or apps for multiple Microsoft 365 platforms including Microsoft 365 Copilot, Microsoft Teams and Microsoft 365. It can significantly ease your development life by providing integrated Microsoft 365 identity, cloud storage access, data from Microsoft Graph, and other services in Azure with a "zero-configuration" approach.
- Cluster: teamsfxaggregation.eastus
- Database: vscode-ext-aggregate

## Conventions & Assumptions

### Time semantics
- Observed timestamp columns:
  - teamsfx_all (VS Code): ServerTimestamp, ClientTimestamp
  - teamsfx_all_cli (CLI): eventTimestamp
  - teamsfx_all_vs (Visual Studio): ClientTimestampUtc
- Canonical Time Column: EventTime
  - Use project-rename patterns to normalize:
    - VS Code: project-rename EventTime = ServerTimestamp (or ClientTimestamp depending on query intent)
    - CLI: project-rename EventTime = eventTimestamp
    - VS: project-rename EventTime = ClientTimestampUtc
- Typical windows and binning:
  - Rolling windows: 28-day rolling dcount via series_fir([1×28])
  - Analysis windows: 90d, 180d, 360d
  - Day granularity: startofday() and in-range by 1d interval
  - Week granularity: startofweek() used for gating current week
  - Month rollups: startofmonth() for funnel aggregation
- Timezone:
  - Unknown overall; Visual Studio explicitly uses ClientTimestampUtc.
  - Default to UTC for cross-source analysis and avoid current day if ingestion lag is unknown.

### Freshness & Completeness Gates
- Current-day data is often excluded:
  - Pattern: where NormalizedTimestamp < startofday(now())
  - endTime = startofday(now()-1d) for safe day-boundary cut.
- F5 success rate has a 3-day “debug grace period” gate:
  - Only consider projects where FirstDebugTime < now()-3d before deeming “blocked”.
- Recommended completeness gate (multi-slice):
  - Use prior full day/week/month.
  - Require a minimum presence across platforms or stage events before counting a conversion (e.g., local-debug-start present before counting publish).
  - Use a sentinel slice count (e.g., ≥2 stage transitions per project) to ensure meaningful engagement.

### Joins & Alignment
- Frequent keys:
  - ProjectId, CorrelationId, MachineId (VSCodeMachineId / machineid / MacAddressHash)
  - ClientVersion (ExtensionVersion / cliversion / ExeVersion)
  - Platform (‘VSC’, ‘CLI’, ‘VS’)
- Typical join kinds:
  - inner: enforce cohort membership (e.g., projects with types or active projects)
  - leftouter: enrich facts with optional dimensions (e.g., Capabilities → AppType)
- Post-join hygiene:
  - Align identity columns:
    - NewProjectId fallback to ProjectId for create events
    - Standardize MachineId across sources
  - Resolve duplicates via distinct, arg_min/arg_max
  - Apply project-away to drop intermediate counters
  - Standardize Success (‘yes’) across sources

### Filters & Idioms
- Internal/test exclusion:
  - VS Code: VSCodeMachineId !in (InternalMachineIds)
  - CLI: machineid !in (InternalMachineIds)
  - Visual Studio: MacAddressHash !in (InternalMachineIds)
  - Visual Studio channel exclusions: ChannelId !in ('VisualStudio.17.IntPreview', 'VisualStudio.17.int.main', 'VisualStudio.16.Preview'), and Properties['context.default.vs.core.hasrootsuffix'] != 'True'
- Version scoping:
  - “v5” cohorts via in (v5StableVersions) or in (v5PreReleaseVersions). Also cliversion/ExtensionVersion regex filters.
- Success flag normalization:
  - Success = 'yes' for conversion stages; otherwise treat as non-conversion.
- Stage normalization:
  - EventName trimmed (‘ms-teams-vscode-extension/’, ‘teamsfx-cli/’) and mapped to funnel stages.
- Allowlist cohort construction:
  - Build sets of ProjectId or CorrelationId first, then join kind=inner to event facts.

### Cross-cluster/DB & Sharding
- Dimension tables from Common DB:
  - cluster('ttk-kusto.eastus').database('Common'): V5StableVersions, V5PrereleaseVersions, Templates, v5Versions, InternalMachineIds
- Fact sources in main DB:
  - cluster('teamsfxaggregation.eastus').database('vscode-ext-aggregate'): teamsfx_all, teamsfx_all_cli, teamsfx_all_vs
- Cross-source union pattern:
  - union VSC, CLI, VS after column normalization (EventTime, MachineId, Success, EventName, ProjectId)
  - Normalize version text and sortable version splits for reporting.

### Table classes
- Fact/event:
  - teamsfx_all, teamsfx_all_cli, teamsfx_all_vs
- Dimension/mapping:
  - v5ProjectType (ProjectId → Capabilities)
  - InternalMachineIds (list of internal machines)
  - V5StableVersions, V5PrereleaseVersions, v5Versions (version cohorts)
  - Templates (template metadata and project associations)

### Important Mapping
- AppType categorization from Capabilities:
  - Bot / Tab / ME (Message Extension) / Copilot / Unknown (regex-based categorization used in queries)
- Funnel stage mapping:
  - 01-Create-Project → create/open/download-sample
  - 02-Local-Debug-Start → debug-all-start / preview-start / local-debug-start
  - 03-Local-Debug → debug-all/preview/local-debug with Success == 'yes'
  - 04-Provision-Start, 05-Provision
  - 06-Publish-Start, 07-Publish (Success == 'yes')
- ReleaseType classification:
  - VS: ChannelId contains Release/Preview; else 'IntPreview'
  - VSC/CLI: regex on ClientVersion → ‘Prerelease’ else ‘Stable’
- Error-type reclassification:
  - Some user error codes are reclassified to system (UserErrorCodeShouldBeSystemType list).

### Notes on Access and Schema
- All get_table_schema calls to the listed clusters/databases failed due to network/auth errors, so the schema tables above are inferred from the provided queries. If you have ADX access, rerun schema retrieval for authoritative columns and types.
- Timezone and refresh delays are not specified. Be conservative with time windows and consider excluding the current day to avoid partial ingestion artifacts.
- For cross-platform analyses, normalize stage names and success semantics:
  - VS Code: debug-all[-start], provision[-start], publish[-start], success from Properties['success'].
  - CLI: preview[-start]/preview, provision[-start]/provision, publish[-start]/publish, success from properties['success'].
  - VS: vs/teamsfx/command/start vs vs/teamsfx/command mapped to local-debug-start/local-debug, provision-start/provision, publish-in-developer-portal-start/publish-in-developer-portal; success inferred as 'yes' on command completion.
- Always exclude InternalMachineIds for external-user metrics unless explicitly analyzing internal usage.

## Entity & Counting Rules (Core Definitions)
- Entity model:
  - Project → Machine → Platform
  - ProjectId: primary entity across all platforms, sometimes created anew (NewProjectId) during template/sample creation; normalize to ProjectId.
  - MachineId: engagement/MAU at user level (VSCodeMachineId / machineid / MacAddressHash).
  - CorrelationId: session-level grouping for funnels and conversion (debug/provision/deploy/publish).
- Counting rules:
  - MAU/app activity:
    - Rolling 28-day active apps via series_fir with a 28-length ones filter; dcount(ProjectId) or dcount(MachineId) depending on KPI definition.
    - Do not sum MAU across time buckets (use rolling windows or dcount per bucket).
  - Active threshold:
    - Example pattern requires ≥2 active days within window to qualify as “active”.
  - F5 success rate:
    - Blocked if IsNeverSuccess = true after the grace period.
    - Analyze by ClientVersion and ErrorCode; use latest error snapshot before first success.
- Do/Don’t:
  - Do normalize identity fields and time before union/join.
  - Don’t mix ProjectId-based and MachineId-based dcount in the same metric without labeling intent.
  - Do exclude internal machines/channels by default.
  - Don’t include current day unless ingestion freshness is validated.

## Views (Reusable Layers)
- Cross-source union pattern:
  - union VSC, CLI, VS after column normalization (EventTime, MachineId, Success, EventName, ProjectId)
  - Normalize version text and sortable version splits for reporting.

- Sharded union
  ```kusto
  let VSC = teamsfx_all | project EventTime = ClientTimestamp, ProjectId = tostring(Properties['project-id']), MachineId = VSCodeMachineId, Success = tostring(Properties['success']), Platform = 'VSC';
  let CLI = teamsfx_all_cli | project EventTime = eventTimestamp, ProjectId = tostring(properties['project-id']), MachineId = machineid, Success = tostring(properties['success']), Platform = 'CLI';
  let VS  = teamsfx_all_vs  | project EventTime = ClientTimestampUtc, ProjectId = tostring(Properties['vs.teamsfx.core.project-id']), MachineId = MacAddressHash, Success = iff(EventName == 'vs/teamsfx/command', 'yes', 'n/a'), Platform = 'VS';

  VSC | union CLI | union VS
  | summarize dcount(ProjectId) by Platform, EventTime = startofday(EventTime)
  ```

- Normalize EventTime across sources
  ```kusto
  // Parameters
  let END_TIME = startofday(now() - 1d);  // Effective end to exclude current day
  let WINDOW = 90d;                       // Adjust: 90d, 180d, 360d as needed
  let START_TIME = END_TIME - WINDOW;
  let INTERVAL = 1d;

  // Normalize EventTime across sources
  let VSC = teamsfx_all
  | where ServerTimestamp >= START_TIME and ServerTimestamp <= END_TIME
  | project EventTime = ServerTimestamp, ProjectId = tostring(Properties['project-id']), MachineId = VSCodeMachineId;

  let CLI = teamsfx_all_cli
  | where eventTimestamp >= START_TIME and eventTimestamp <= END_TIME
  | project EventTime = eventTimestamp, ProjectId = tostring(properties['project-id']), MachineId = machineid;

  let VS = teamsfx_all_vs
  | where ClientTimestampUtc >= START_TIME and ClientTimestampUtc <= END_TIME
  | project EventTime = ClientTimestampUtc, ProjectId = tostring(Properties['vs.teamsfx.core.project-id']), MachineId = MacAddressHash;
  ```

## Query Building Blocks (Copy-paste snippets, contains snippets and description)

- Time window template
  - Description: Set safe analysis windows, exclude current day to avoid partial ingestion. Use rolling windows for MAU-like metrics.
  - Query snippets:
    ```kusto
    // Parameters
    let END_TIME = startofday(now() - 1d);  // Effective end to exclude current day
    let WINDOW = 90d;                       // Adjust: 90d, 180d, 360d as needed
    let START_TIME = END_TIME - WINDOW;
    let INTERVAL = 1d;

    // Normalize EventTime across sources
    let VSC = teamsfx_all
    | where ServerTimestamp >= START_TIME and ServerTimestamp <= END_TIME
    | project EventTime = ServerTimestamp, ProjectId = tostring(Properties['project-id']), MachineId = VSCodeMachineId;

    let CLI = teamsfx_all_cli
    | where eventTimestamp >= START_TIME and eventTimestamp <= END_TIME
    | project EventTime = eventTimestamp, ProjectId = tostring(properties['project-id']), MachineId = machineid;

    let VS = teamsfx_all_vs
    | where ClientTimestampUtc >= START_TIME and ClientTimestampUtc <= END_TIME
    | project EventTime = ClientTimestampUtc, ProjectId = tostring(Properties['vs.teamsfx.core.project-id']), MachineId = MacAddressHash;
    ```

- Join template
  - Description: Enrich fact events with project type and version cohorts; use inner for strict cohorts and leftouter for optional enrichment.
  - Query snippets:
    ```kusto
    // Version cohorts (Common DB)
    let StableVersions = cluster('ttk-kusto.eastus').database('Common').V5StableVersions;
    let PreReleaseVersions = cluster('ttk-kusto.eastus').database('Common').V5PrereleaseVersions;

    // Project type dimension
    let ProjectTypes = v5ProjectType
    | where Capabilities != ''
    | project ProjectId, AppType = tostring(Capabilities);

    // Events filtered to v5 cohorts
    let VSCv5 = teamsfx_all
    | where ExtensionVersion in (StableVersions) or ExtensionVersion in (PreReleaseVersions)
    | extend ProjectId = tostring(Properties['project-id']);

    // Inner join for cohort membership, leftouter for optional enrichment
    VSCv5
    | join kind=inner ProjectTypes on ProjectId
    | project ProjectId, AppType, ExtensionVersion, ClientTimestamp
    ```

- De-dup pattern
  - Description: Remove duplicates and select first/last records per entity; handle dirty VS data and session-level summaries.
  - Query snippets:
    ```kusto
    // Remove duplicated VS events caused by noisy ingestion
    teamsfx_all_vs
    | distinct ClientTimestampUtc, EventName, ExeVersion, MacAddressHash, Properties

    // First/last by correlation/session
    someEvents
    | summarize (_, FirstVersion, FirstMachine) = arg_min(EventTime, Version, MachineId)
             , (LastTime, LastEventName)      = arg_max(EventTime, EventName)
      by CorrelationId

    // First success before a cutoff
    someEvents
    | summarize FirstSuccessTime = minif(EventTime, Success == 'yes') by ProjectId
    ```

- Important filters
  - Description: Default exclusions and stable/prerelease cohorts; stage gating filters; internal channel filters.
  - Query snippets:
    ```kusto
    // Exclude internal machines
    | where VSCodeMachineId !in (InternalMachineIds)
    // VS channels exclusion
    | where ChannelId !in ('VisualStudio.17.IntPreview', 'VisualStudio.17.int.main', 'VisualStudio.16.Preview')
    | where Properties['context.default.vs.core.hasrootsuffix'] != 'True'
    // v5 cohort inclusion
    | where ExtensionVersion in (v5StableVersions) or ExtensionVersion in (v5PreReleaseVersions)
    // Success normalization
    | where Success == 'yes'
    ```

- Important Definitions
  - Description: Standard domain definitions for reuse in metrics.
  - Snippets:
    ```kusto
    // F5 “blocked” definition with grace period
    let LatestFirstDebugTime = now() - 3d;
    let ProjectFirstDebugSessions = v5AllValidSessions
    | summarize FirstDebugTime = min(EventTime) by ProjectId;
    v5AllValidSessions
    | join kind=leftouter ProjectFirstDebugSessions on ProjectId
    | extend ConsiderForF5 = FirstDebugTime < LatestFirstDebugTime
    | extend Blocked = IsNeverSuccess and ConsiderForF5
    ```

- ID parsing/derivation
  - Description: Normalize project IDs and event names; unify “create” ID source and “trim” prefixes.
  - Query snippets:
    ```kusto
    // Normalize ProjectId during create events
    | extend NewProjectId = tostring(Properties['new-project-id'])
    | extend ProjectId = iff(isempty(NewProjectId), tostring(Properties['project-id']), NewProjectId)

    // Trim event prefixes to canonical EventName
    | extend EventName = trim_start('ms-teams-vscode-extension/', EventName)
    | extend EventName = trim_start('teamsfx-cli/', name)
    ```

- Sharded union
  - Description: Union across VSC, CLI, VS after normalizing column names and types; then summarize by entity/time.
  - Query snippets:
    ```kusto
    let VSC = teamsfx_all | project EventTime = ClientTimestamp, ProjectId = tostring(Properties['project-id']), MachineId = VSCodeMachineId, Success = tostring(Properties['success']), Platform = 'VSC';
    let CLI = teamsfx_all_cli | project EventTime = eventTimestamp, ProjectId = tostring(properties['project-id']), MachineId = machineid, Success = tostring(properties['success']), Platform = 'CLI';
    let VS  = teamsfx_all_vs  | project EventTime = ClientTimestampUtc, ProjectId = tostring(Properties['vs.teamsfx.core.project-id']), MachineId = MacAddressHash, Success = iff(EventName == 'vs/teamsfx/command', 'yes', 'n/a'), Platform = 'VS';

    VSC | union CLI | union VS
    | summarize dcount(ProjectId) by Platform, EventTime = startofday(EventTime)
    ```

## Example Queries (with explanations)

- 2023 New OKR 2.2: F5 success rate; By version and project type
  - Description: Computes F5 success rate across VSC/CLI/VS with a 3-day grace period and reclassifies certain user error codes as system. It normalizes versions, deduplicates sessions per CorrelationId, and outputs two tags: errors (IsNeverSuccess) and success rate.
  - Adaptations: change LatestFirstDebugTime window, filter by ProjectType/AppType, or scope Version cohorts. Avoid summing success rates across time; prefer per-version comparisons.
  - The app used to calculate F5 success rate should meet these criteria:
    - Debugging grace period: Only consider the app for F5 success rate analysis if the date between the current day and the app’s first debugging event is at least 3 days. This allows users up to 3 days to complete local debugging before the system assumes potential blocking issues.
    - Blocked app condition: An app is considered blocked if it has never had a successful F5 run (IsNeverSuccess = true).
      
  ```kusto
  // 2023 New OKR 2.2: F5 success rate
  // By version and project type
  let DurationThreshold = 60min; // Time >= DurationThreshold counts as infinity
  let LatestFirstDebugTime = now() - 3d; // Give users 3 days to finish local debug before assuming they are blocked
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
  ]; // these error codes are user type but should categrized into system type in BI.
  //+++++++++++++++++++++++++++++++++++++++++
  // Query VSC V4 Projects
  //+++++++++++++++++++++++++++++++++++++++++
  let V4Projects = teamsfx_all
  | where ExtensionVersion startswith '4.'
  // | where EventName == 'ms-teams-vscode-extension/debug-all' 
  // | where Properties ['success'] == 'yes'
  | extend ProjectId = tostring(Properties['project-id'])
  | distinct ProjectId;
  //+++++++++++++++++++++++++++++++++++++++++
  // Query VSC V5 Projects
  //+++++++++++++++++++++++++++++++++++++++++
  let VSCv5AllValidSessions = teamsfx_all
  // Make the version sortable
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
  | where
      (Name == 'debug-all') or
      (Name == 'debug-prerequisites') or
      (Name == 'metadata') or
      (Name == 'lifecycle-execution')
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
      // No need to trans error message as the message for PrerequisitesValidationError is not useful
      ErrorCode = tostring(
              case(
                  ErrorCode != 'Ext.PrerequisitesValidationError', ErrorCode,
                  CheckResults['ports occupancy'].result == 'failed', strcat_delim(
                      '.',
                      CheckResults['ports occupancy'].source,
                      // keep same value as the one defined in latest TTK
                      'PortsConflictError'
                  ),
                  CheckResults['Microsoft 365 Account'].result == 'failed', strcat_delim(
                      '.',
                      CheckResults['Microsoft 365 Account'].source,
                      CheckResults['Microsoft 365 Account'].errorCode
                  ),
                  ErrorCode
              )
          )
  | extend IsInternalUser = MachineId in (InternalMachineIds) 
  | project-away DebugAllCount, TestToolCount
  | extend ClientName = 'VSC';
  //+++++++++++++++++++++++++++++++++++++++++
  // Query CLI V5 Projects
  //+++++++++++++++++++++++++++++++++++++++++
  let CLIv5AllValidSessions = teamsfx_all_cli
  // Make the version sortable
  | extend VersionArr = split(cliversion, '.')
  | extend Version = toint(VersionArr[0])*10000 + toint(VersionArr[1])*100 + toint(VersionArr[2])
  | where cliversion in (v5Versions) and cliversion matches regex @'\d+\.\d+\.\d$'
  | extend 
      Name = tostring(split(name, '/')[1]),
      ProjectId = tostring(properties['project-id']),
      Duration = todouble(measures['duration']) * 1s,
      IsSuccess = properties['success'] == 'yes',
      CheckResults = parse_json(tostring(properties['debug-check-results-safe'])),
      CorrelationId = tostring(properties['correlation-id'])
  | where isnotempty(CorrelationId) and CorrelationId != 'no-session-id'
  | where
      (Name == 'preview') or
      (Name == 'preview-prerequisites') or
      (Name == 'metadata') or
      (Name == 'lifecycle-execution')
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
  | extend
      IsSuccess = DebugSuccess
  | extend IsInternalUser = MachineId in (InternalMachineIds)
  | project-away DebugAllCount
  | extend ClientName = 'CLI';
  //+++++++++++++++++++++++++++++++++++++++++
  // Query ProjectType
  //+++++++++++++++++++++++++++++++++++++++++
  let VSCV5TemplateAndSample = teamsfx_all
  // Make the version sortable
  | extend Name = tostring(split(EventName, '/')[1])
  | where ExtensionName == 'ms-teams-vscode-extension' 
      and ExtensionVersion in (v5Versions)
      and (
              Name == 'create-project'
              or Name == 'download-sample'
      )
  | extend ProjectId = tostring(Properties['new-project-id'])
  | summarize 
      (_, ClientVersion) = arg_min(ClientTimestamp, ExtensionVersion)
      by ProjectId, ExtensionVersion
  | extend ClientName = 'VSC'
  | project ProjectId, ClientVersion, ClientName
  ;
  let CLIV5TemplateAndSample = teamsfx_all_cli
  | where cliversion in (v5Versions) and cliversion matches regex @'\d+\.\d+\.\d$'
  | extend Name = tostring(split(name, '/')[1])
  | where Name == 'create-project' or Name == 'download-sample'
  | extend ProjectId = tostring(properties['new-project-id'])
  | summarize
      (_, ClientVersion) = arg_min(eventTimestamp, cliversion)
      by ProjectId, cliversion
  | extend ClientName = 'CLI'
  | project ProjectId, ClientVersion, ClientName
  ;
  let V5AllTemplateAndSample = VSCV5TemplateAndSample
  | union CLIV5TemplateAndSample;
  let V5ProjectTypes = v5ProjectType
  | where Capabilities != ''
  | project ProjectId, AppType=tostring(Capabilities)
  ;
  let V5AllProjectType = V5AllTemplateAndSample
  | join kind = inner V5ProjectTypes on ProjectId
  | summarize by ProjectId, AppType, ClientVersion
  | extend LowerAppType = tolower(AppType)
  | extend
     ProjectType = tostring(
          case(
              // ai-bot will be categrize to 'Bot'
              LowerAppType matches regex @'\b(bot|adaptive-card|notification|botandmessageextension|tabnonssoandbot)\b', 'Bot',
              LowerAppType matches regex @'\b(tab|dashboard|todo-list|sso-launch-page|hello-world-in-meeting|graph-toolkit|graph-connector-app|live-share-dice-roller|outlook-add-in-set-signature|share-now|intelligent-data-chart-generator)\b', 'Tab',
              LowerAppType matches regex @'\b(message-extension|messageextension|msgext|search-app|link-unfurling|npm-search-connector-m365)\b', 'ME',
              LowerAppType matches regex @'\b(copilot|api-plugin|declarative-agent)\b', 'Copilot',
              // To be done
              // LowerAppType matches regex @'\b(taskpane|outlook-addin-import)\b', 'OutlookAddIn',
              'Unknown'
          )
      )
  | project ProjectId, ProjectType, ClientVersion
  ;
  //+++++++++++++++++++++++++++++++++++++++++
  // Merge VSC and CLI project
  //+++++++++++++++++++++++++++++++++++++++++
  let v5AllValidSessions = VSCv5AllValidSessions
  | union CLIv5AllValidSessions;
  let ProjectFirstDebugSessions = v5AllValidSessions
  | summarize FirstDebugTime = min(Timestamp) by ProjectId, IsTestTool
  ;
  let ProjectFirstSuccessSessions = v5AllValidSessions
  | where DebugSuccess
  // Do not summarize by version because first success means first in all versions.
  | summarize FirstSuccessTime = min(Timestamp) by ProjectId, ClientName, IsTestTool
  ;
  let v5AllBeforeFirstSuccessSessions = v5AllValidSessions
  | join kind=leftouter ProjectFirstSuccessSessions on ProjectId, ClientName, IsTestTool
  | extend IsNeverSuccess = isempty(FirstSuccessTime)
  | where IsNeverSuccess or Timestamp <= FirstSuccessTime
  | join kind=leftouter ProjectFirstDebugSessions on ProjectId, IsTestTool
  | where FirstDebugTime < LatestFirstDebugTime
  | join kind=leftouter V5AllProjectType on ProjectId
  | extend ProjectType = iff(isempty(ProjectType), 'Unknown', ProjectType)
  // filter out v4
  // There are still some projects(count: 127) created by v4 currently(10/28/2024), so keep this condition.
  | where ProjectId !in (V4Projects)
  ;
  let v5ProjectData = v5AllBeforeFirstSuccessSessions
  | summarize
      IsNeverSuccess = take_any(IsNeverSuccess),
      (Timestamp, ErrorCode, ErrorMessage, ErrorType) = arg_max(Timestamp, ErrorCode, ErrorMessage, ErrorType),
      (_, ClientVersion, MachineId, IsInternalUser) = arg_min(Timestamp, ClientVersion, MachineId, IsInternalUser),
      ProjectType = take_any(ProjectType)
      by ProjectId, ClientName, IsTestTool
  | extend ClientVersionArr = split(ClientVersion, '.')
  // make the version sortable in BI page
  | extend VersionMajor = tostring(ClientVersionArr[0]), VersionMinor = tostring(ClientVersionArr[1]), VersionPatch = tostring(ClientVersionArr[2])
  | extend VersionMinor = iif(toint(VersionMinor) < 10, strcat('0', VersionMinor), VersionMinor)
  | extend ClientVersion = strcat(tostring(VersionMajor), '.', tostring(VersionMinor), '.', VersionPatch)
  | extend ErrorType = iif(ErrorType == 'user' and ErrorCode in (UserErrorCodeShouldBeSystemType), 'system', ErrorType)
  | project ProjectId, ClientName, ClientVersion, MachineId, IsInternalUser, IsTestTool, Timestamp, ErrorCode, ErrorMessage, IsNeverSuccess, ProjectType, ErrorType
  ;
  let v5Errors = v5ProjectData
  | where IsNeverSuccess
  | extend Tag = 'error';
  let v5SuccessRate = v5ProjectData
  | extend Tag = 'SuccessRate';
  //+++++++++++++++++++++++++++++++++++++++++
  // Query VS Projects
  //+++++++++++++++++++++++++++++++++++++++++
  let TimestampInfinity = datetime(2100, 1, 1);
  let V5Version = toscalar(v5Versions | summarize make_set(Version)); // filter out V5 prerelease
  // Step 1: Cleanup data
  let VSDataClean = teamsfx_all_vs 
  | where ExeVersion !in (v5Versions)
  | extend VersionMajor = toint(split(ExeVersion, '.')[0]), VersionMinor = toint(split(ExeVersion, '.')[1])
  // filter out version < 17.6
  | where VersionMajor >= 17 and VersionMinor >= 6 
  | extend 
      Name = tostring(Properties['vs.teamsfx.name']),
      CorrelationId = tostring(Properties['vs.teamsfx.core.correlation-id']),
      ProjectId = tostring(Properties['vs.teamsfx.core.project-id']),
      IsInternalUser = Properties['context.default.vs.core.user.isvslogininternal'] == 'true',
      IsManifestMetadata = isnotempty(Properties['vs.teamsfx.core.manifest.id']),
      CoreEvent = tostring(Properties['vs.teamsfx.core.event']),
      NewProjectId = tostring(Properties['vs.teamsfx.core.new-project-id']),
      Component = iff(
          Properties['vs.teamsfx.core.component'] == 'fx-resource-dotnet', // tab project was 'fx-resource-dotnet' before GA
          'fx-resource-frontend-hosting', 
          tostring(Properties['vs.teamsfx.core.component'])
      ),
      ErrorMessage = tostring(Properties['reserved.datamodel.fault.description']),
      IsManifestEvent = EventName == 'vs/teamsfx/core' and Properties['vs.teamsfx.core.event'] == 'metadata' and isnotempty(Properties['vs.teamsfx.core.manifest.id'])
  | where isnotempty(ProjectId)
  | distinct ClientTimestampUtc, CoreEvent, CorrelationId, Component, EventName, EventId, ExeVersion, MacAddressHash, IsInternalUser, Name, NewProjectId, ProjectId, ErrorMessage, ChannelId, IsManifestMetadata // dedup because there are dirty data in VS database
  | extend MachineId = MacAddressHash
  | extend VersionMajor = tostring(split(ExeVersion, '.')[0]), VersionMinor = tostring(split(ExeVersion, '.')[1])
  // make the version sortable in BI page
  | extend VersionMinor = iif(toint(VersionMinor) < 10, strcat('0', VersionMinor), VersionMinor)
  | extend VersionMajorMinor = strcat(VersionMajor, '.', VersionMinor)
  ;
  // Step 2. Calculate duration for 'DebugProject' (The deployment step in F5)
  let VSDebugProjectEvents = VSDataClean
  | where isnotempty(ProjectId)
  | where Name == 'DebugProject'
  | order by ClientTimestampUtc asc
  | serialize 
  | extend StartTime = iff(prev(ProjectId, 1) == ProjectId and prev(EventName, 1) == 'vs/teamsfx/command/start' and prev(Name, 1) == 'DebugProject', prev(ClientTimestampUtc, 1), datetime(null))
  | extend IsSuccess = EventName == 'vs/teamsfx/command'
  | extend StartEventNotFound = isempty(StartTime)
  | extend Duration = (ClientTimestampUtc - StartTime)
  ;
  // Step 3. Calculate duration for 'Debug' (The 'Prepare Teamsfx environment' command in file tree)
  let VSPrepareDebugEvents = VSDataClean
  | where isnotempty(ProjectId)
  | where Name == 'Debug'
  | order by ClientTimestampUtc asc
  | serialize 
  | extend StartTime = iff(prev(ProjectId, 1) == ProjectId and prev(EventName, 1) == 'vs/teamsfx/command/start' and prev(Name, 1) == 'Debug', prev(ClientTimestampUtc, 1), datetime(null))
  | extend IsSuccess = EventName == 'vs/teamsfx/command'
  | extend StartEventNotFound = isempty(StartTime)
  | extend Duration = (ClientTimestampUtc - StartTime)
  ;
  let VSAllDebugEvents = VSDebugProjectEvents
  | union VSPrepareDebugEvents
  ;
  // Step 4: Calculate the first successful F5 timestamp
  let VSProjectFirstSuccessSessions = VSDebugProjectEvents
  | summarize 
      (FirstSuccessTime, FirstSuccessExeVersion) = arg_min(iff(IsSuccess, ClientTimestampUtc, TimestampInfinity+1d), ExeVersion),
      LastDebugTime = max(ClientTimestampUtc)
      by ProjectId
  | extend FirstSuccessTime = iff(FirstSuccessTime > TimestampInfinity, datetime(null), FirstSuccessTime) // Kusto does not have arg_min_if
  ;
  // Step 5: Summarize all F5 and Prepare local environment duration before first success timestamp.
  let VSAllBeforeFirstSuccessEvents = VSAllDebugEvents
  | join kind=leftouter v5ProjectType on ProjectId
  | extend ProjectType = tostring(
      case(
              // ai-bot will be categrize to 'Bot'
              Capabilities matches regex @'\b(bot|adaptive-card|notification|botandmessageextension|tabnonssoandbot)\b', 'Bot',
              Capabilities matches regex @'\b(tab|dashboard|todo-list|sso-launch-page|hello-world-in-meeting|graph-toolkit|graph-connector-app|live-share-dice-roller|outlook-add-in-set-signature|share-now|intelligent-data-chart-generator)\b', 'Tab',
              Capabilities matches regex @'\b(message-extension|messageextension|msgext|search-app|link-unfurling|npm-search-connector-m365)\b', 'ME',
              Capabilities matches regex @'\b(copilot|api-plugin|declarative-agent)\b', 'Copilot',
              // To be done
              // Capabilities matches regex @'\b(taskpane|outlook-addin-import)\b', 'OutlookAddIn',
              'Unknown'
          )
  )
  | join kind=leftouter VSProjectFirstSuccessSessions on ProjectId
  | extend IsNeverSuccess = isempty(FirstSuccessTime)
  | where IsNeverSuccess or ClientTimestampUtc <= FirstSuccessTime
  ;
  // Step 6: Calculate the final aggregation data
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
      (LastEventTime, LastEventName, LastCommandName, LastErrorMessage, MachineId, IsInternalUser) = 
          arg_max(ClientTimestampUtc, EventName, Name, ErrorMessage, MachineId, IsInternalUser),
      ProjectType = take_any(ProjectType)
      by ProjectId, VersionMajorMinor, ChannelId
  | extend DurationBeforeSuccess = iff(IsNeverSuccess, DurationThreshold, Duration)
  | extend LastErrorMessage = iff(isempty(LastErrorMessage), '<User successfully prepared but never hits F5>', LastErrorMessage)
  | extend Timestamp = LastEventTime
  // No column for ErrorType, set a default value
  | extend ErrorType = iif(IsNeverSuccess, 'system', '')
  ;
  let VSErrors = VSResult
  | where IsNeverSuccess
  | project ClientName = 'VS', ClientVersion = VersionMajorMinor, ProjectId, MachineId, IsInternalUser, ErrorMessage = LastErrorMessage, ErrorCode = substring(LastErrorMessage, 0, 50), Tag = 'error', ChannelId, ProjectType, Timestamp, ErrorType
  ;
  let VSSuccessRate = VSResult
  | project ClientName = 'VS', ClientVersion = VersionMajorMinor, ProjectId, MachineId, IsInternalUser, Tag = 'SuccessRate', IsNeverSuccess, ChannelId, ProjectType, Timestamp, ErrorType
  ;
  //+++++++++++++++++++++++++++++++++++++++++
  // Merge VS and VSC/CLI project
  //+++++++++++++++++++++++++++++++++++++++++
  union v5Errors, v5SuccessRate,
      VSErrors, VSSuccessRate
  | extend ReleaseType = 
      iff(ClientName == 'VS', 
          iff(ChannelId contains_cs 'Release', 'Stable',
              iff(ChannelId contains_cs 'Preview', 'Preview', 'IntPreview')),
          iff(ClientVersion matches regex '\d+\.\d+\.\d{3,10}', 'Prerelease', 'Stable'))
  | extend IsTestTool = iff(isempty(IsTestTool), false, IsTestTool)
  ```

- // OKR_App_MAU_all
  - Description: Rolling 28-day number of apps that have ever opened with Teams Toolkit across VSC/CLI/VS. Excludes internal machines and current day, unions normalized EventTime, and computes per-project daily activity before rolling aggregation. Adapt: adjust WINDOW (e.g., 360d) and INTERVAL; ensure exclusion of current day.
  ```kusto
  // OKR 1: # of apps that have ever opened with TTK
  let END_TIME=startofday(now()-0d);
  let WINDOW=360d;
  let START_TIME=END_TIME-WINDOW;
  let INTERVAL=1d;
  let allProjects = teamsfx_all
  | where ExtensionName == "ms-teams-vscode-extension"
  | where VSCodeMachineId !in (InternalMachineIds)
  | extend ProjectId = tostring(Properties["project-id"])
  | summarize by ProjectId
  | union (
      teamsfx_all_cli
      | where name startswith "teamsfx-cli"
      | where machineid !in (InternalMachineIds)
      | extend ProjectId = tostring(properties["project-id"])
      | summarize by ProjectId
  )
  | union (
      teamsfx_all_vs
      | where EventName startswith "vs/teamsfx"
      | where MacAddressHash !in (InternalMachineIds)
      | extend ProjectId = tostring(Properties["vs.teamsfx.core.project-id"])
      | summarize by ProjectId
  )
  | where isnotempty(ProjectId);
  teamsfx_all
  | where ExtensionName == "ms-teams-vscode-extension" and ServerTimestamp >= START_TIME and ServerTimestamp <= END_TIME
  | where ExtensionVersion matches regex @'\b([2-9]|[1-9][0-9])\.\d+\.\d$'
  | extend TimeStamp = ServerTimestamp, ProjectId = tostring(Properties['project-id'])
  | union (
      teamsfx_all_cli
      | where name startswith "teamsfx-cli" and eventTimestamp >= START_TIME and eventTimestamp <= END_TIME
      | extend TimeStamp = eventTimestamp, ProjectId = tostring(properties["project-id"])
      )
  | union (
      teamsfx_all_vs
      | where EventName startswith "vs/teamsfx" and ClientTimestampUtc >= START_TIME and ClientTimestampUtc <= END_TIME
      | extend TimeStamp = ClientTimestampUtc, ProjectId = tostring(Properties['vs.teamsfx.core.project-id'])
      )
  | where ProjectId in (allProjects)
  | make-series Num=dcount(ProjectId) default=0
  on TimeStamp in range(START_TIME, END_TIME-1s, INTERVAL) by ProjectId // Active days for each project
  | extend Numd=series_fir(Num, dynamic([1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1]))
  | project ProjectId, z=zip(TimeStamp, Numd) 
  | mv-expand z
  | extend Timestamp=todatetime(z[0]), Numdb=iff(todouble(z[1]) > 0.0, 1, 0)
  | extend All="All"
  | make-series rolling_dcount=sum(Numdb) default=0
  on Timestamp in range(START_TIME, END_TIME, INTERVAL) by All
  | extend NormalizedRollingDcount=array_slice(rolling_dcount,28,-1), NormalizedTimestamp=array_slice(Timestamp, 28,-1)
  | project NormalizedRollingDcount, NormalizedTimestamp
  | mv-expand NormalizedRollingDcount, NormalizedTimestamp
  | extend NormalizedTimestamp = todatetime(NormalizedTimestamp)
  | where NormalizedTimestamp < startofday(now())
  | order by NormalizedTimestamp
  ```

- // OKR_App_MAU_all_total
  - Description: Total number of apps that have ever opened (distinct ProjectId) across platforms excluding internal machines; snapshot count, not time series. Adapt: filter cohort windows or platforms as needed.
  ```kusto
  // OKR 1: # of apps that have ever opened with TTK
  let END_TIME=startofday(now()-0d);
  let WINDOW=360d;
  let START_TIME=END_TIME-WINDOW;
  let INTERVAL=1d;
  let allProjects = teamsfx_all
  | where ExtensionName == "ms-teams-vscode-extension"
  | where VSCodeMachineId !in (InternalMachineIds)
  | extend ProjectId = tostring(Properties["project-id"])
  | summarize by ProjectId
  | union (
      teamsfx_all_cli
      | where name startswith "teamsfx-cli"
      | where machineid !in (InternalMachineIds)
      | extend ProjectId = tostring(properties["project-id"])
      | summarize by ProjectId
  )
  | union (
      teamsfx_all_vs
      | where EventName startswith "vs/teamsfx"
      | where MacAddressHash !in (InternalMachineIds)
      | extend ProjectId = tostring(Properties["vs.teamsfx.core.project-id"])
      | summarize by ProjectId
  )
  | where isnotempty(ProjectId);
  allProjects
  | summarize by ProjectId
  | count;
  ```

- // OKR_App_MAU_develop
  - Description: Rolling 28-day number of apps that performed development actions (create, debug, provision, deploy, publish, build, etc.). Excludes internal machines. Adapt: customize the event set to your definition of “developed”.
  ```kusto
  // OKR 1: # of apps that have ever developed with TTK
  let END_TIME=startofday(now()-0d);
  let WINDOW=360d;
  let START_TIME=END_TIME-WINDOW;
  let INTERVAL=1d;
  let developProjects = teamsfx_all
  | where ExtensionName == "ms-teams-vscode-extension"
  | where EventName in (
      'ms-teams-vscode-extension/open-teams-app',
      'ms-teams-vscode-extension/create-project',
      'ms-teams-vscode-extension/local-debug',
      'ms-teams-vscode-extension/debug-all',
      'ms-teams-vscode-extension/provision',
      'ms-teams-vscode-extension/deploy',
      'ms-teams-vscode-extension/publish',
      'ms-teams-vscode-extension/build',
      'ms-teams-vscode-extension/update-teams-app',
      'ms-teams-vscode-extension/open-manifest-editor'
      )
  | extend ProjectId = tostring(Properties["project-id"])
  | where VSCodeMachineId !in (InternalMachineIds)
  | summarize by ProjectId
  | union (
      teamsfx_all_cli
      | where name startswith "teamsfx-cli"
      | where name in (
          'teamsfx-cli/open-teams-app',
          'teamsfx-cli/create-project',
          'teamsfx-cli/local-debug',
          'teamsfx-cli/debug-all',
          'teamsfx-cli/provision',
          'teamsfx-cli/deploy',
          'teamsfx-cli/publish',
          'teamsfx-cli/build',
          'teamsfx-cli/update-teams-app',
          'teamsfx-cli/open-manifest-editor'
          )
      | extend ProjectId = tostring(properties["project-id"])
      | where machineid !in (InternalMachineIds)
      | summarize by ProjectId
      )
  | union (
      teamsfx_all_vs
      | where EventName startswith "vs/teamsfx"
      | where Properties["vs.teamsfx.name"] in (
          'Provision',
          'Deploy',
          'CreateProject',
          'Debug',
          'RegisterTeamsApp',
          'EditManifest',
          'Preview',
          'DeployManifest',
          'DebugProject'
          )
      | extend ProjectId = tostring(Properties['vs.teamsfx.core.project-id'])
      | where MacAddressHash !in (InternalMachineIds)
      | summarize by ProjectId
      )
  | where isnotempty(ProjectId);
  teamsfx_all
  | where ExtensionName == "ms-teams-vscode-extension" and ServerTimestamp >= START_TIME and ServerTimestamp <= END_TIME
  | where ExtensionVersion matches regex @'\b([2-9]|[1-9][0-9])\.\d+\.\d$'
  | extend TimeStamp = ServerTimestamp, ProjectId = tostring(Properties['project-id'])
  | union (
      teamsfx_all_cli
      | where name startswith "teamsfx-cli" and eventTimestamp >= START_TIME and eventTimestamp <= END_TIME
      | extend TimeStamp = eventTimestamp, ProjectId = tostring(properties["project-id"])
      )
  | union (
      teamsfx_all_vs
      | where EventName startswith "vs/teamsfx" and ClientTimestampUtc >= START_TIME and ClientTimestampUtc <= END_TIME
      | extend TimeStamp = ClientTimestampUtc, ProjectId = tostring(Properties['vs.teamsfx.core.project-id'])
      )
  | where ProjectId in (developProjects)
  | make-series Num=dcount(ProjectId) default=0
  on TimeStamp in range(START_TIME, END_TIME-1s, INTERVAL) by ProjectId // Active days for each project
  | extend Numd=series_fir(Num, dynamic([1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1]))
  | project ProjectId, z=zip(TimeStamp, Numd) 
  | mv-expand z
  | extend Timestamp=todatetime(z[0]), Numdb=iff(todouble(z[1]) > 0.0, 1, 0)
  | extend All="All"
  | make-series rolling_dcount=sum(Numdb) default=0
  on Timestamp in range(START_TIME, END_TIME, INTERVAL) by All
  | extend NormalizedRollingDcount=array_slice(rolling_dcount,28,-1), NormalizedTimestamp=array_slice(Timestamp, 28,-1)
  | project NormalizedRollingDcount, NormalizedTimestamp
  | mv-expand NormalizedRollingDcount, NormalizedTimestamp
  | extend NormalizedTimestamp = todatetime(NormalizedTimestamp)
  | where NormalizedTimestamp < startofday(now())
  | order by NormalizedTimestamp
  ```

- // Templates_Follow_Ups
  - Description: Joins template projects with follow-up events (provision, deploy, debug) across platforms using CorrelationId, classifies version type (Stable/PreRelease), and outputs per-project event outcomes. Adapt: scope to specific template names/categories; use Time and Version filters.
  ```kusto
  let TESTTOOLENV = dynamic([
      "c585cf93fbff733898e3e58c67bc041f02e3b0c913993a1cba724f45b9d321f1",
      "f3cc87f78b21d53dcccd34b6dd0c2e8679cb5e6ea3ad600e2689015ce100825a"
  ]);
  let StableVersion = cluster('ttk-kusto.eastus').database('Common').V5StableVersions;
  let PreReleaseVersion = cluster('ttk-kusto.eastus').database('Common').V5PrereleaseVersions;
  let template_projecIds = cluster('ttk-kusto.eastus').database('Common').Templates
  | summarize by ProjectId;
  let common_corIds = cluster('teamsfxaggregation.eastus').database('vscode-ext-aggregate').teamsfx_all
  | extend ProjectId = tostring(Properties["project-id"]), CorrelationId = tostring(Properties["correlation-id"])
  | where ProjectId in (template_projecIds)
  | summarize DebugAllStartCount = countif(EventName == "ms-teams-vscode-extension/debug-all-start"), ProvisionCount = countif(EventName == "ms-teams-vscode-extension/provision"), DeployCount = countif(EventName == "ms-teams-vscode-extension/deploy") by CorrelationId
  | summarize ProvisionLocalCount = countif(DebugAllStartCount > 0 and ProvisionCount >= 0), ProvisionRemoteCount = countif(DebugAllStartCount == 0 and ProvisionCount > 0), DeployCount = countif(DebugAllStartCount == 0 and DeployCount > 0) by CorrelationId
  | summarize by CorrelationId, ProvisionLocalCount, ProvisionRemoteCount, DeployCount
  | union (
      cluster('teamsfxaggregation.eastus').database('vscode-ext-aggregate').teamsfx_all_cli
      | extend ProjectId = tostring(properties["project-id"]), CorrelationId = tostring(properties["correlation-id"])
      | where ProjectId in (template_projecIds)
      | summarize DebugAllStartCount = countif(name == "teamsfx-cli/debug-all-start"), ProvisionCount = countif(name == "teamsfx-cli/provision"), DeployCount = countif(name == "teamsfx-cli/deploy") by CorrelationId
      | summarize ProvisionLocalCount = countif(DebugAllStartCount > 0 and ProvisionCount >= 0), ProvisionRemoteCount = countif(DebugAllStartCount == 0 and ProvisionCount > 0), DeployCount = countif(DebugAllStartCount == 0 and DeployCount > 0) by CorrelationId
      | summarize by CorrelationId, ProvisionLocalCount, ProvisionRemoteCount, DeployCount
  );
  let debug_playground_corIds = cluster('teamsfxaggregation.eastus').database('vscode-ext-aggregate').teamsfx_all
  | extend ProjectId = tostring(Properties["project-id"]), CorrelationId = tostring(Properties["correlation-id"]), Env = tostring(Properties["env.teamsfx_env"])
  | where ProjectId in (template_projecIds) and EventName == "ms-teams-vscode-extension/metadata" and Env in (TESTTOOLENV)
  | summarize by CorrelationId
  | union (
      cluster('teamsfxaggregation.eastus').database('vscode-ext-aggregate').teamsfx_all_cli
      | extend ProjectId = tostring(properties["project-id"]), CorrelationId = tostring(properties["correlation-id"]), Env = tostring(properties["env.teamsfx_env"])
      | where ProjectId in (template_projecIds) and name == "teamsfx-cli/metadata" and Env in (TESTTOOLENV)    
      | summarize by CorrelationId
  );
  let provision_corIds = common_corIds
  | where ProvisionRemoteCount > 0
  | summarize by CorrelationId
  | union (
      cluster('teamsfxaggregation.eastus').database('vscode-ext-aggregate').teamsfx_all_vs
      | extend Name = tostring(Properties['vs.teamsfx.name']), CorrelationId = tostring(Properties["vs.teamsfx.core.correlation-id"])
      | where Name == "Provision"
      | summarize by CorrelationId
  );
  let debug_corIds = common_corIds
  | where ProvisionLocalCount > 0
  | summarize by CorrelationId
  | union (
      cluster('teamsfxaggregation.eastus').database('vscode-ext-aggregate').teamsfx_all_vs
      | extend Name = tostring(Properties['vs.teamsfx.name']), CorrelationId = tostring(Properties["vs.teamsfx.core.correlation-id"])
      | where Name == "Debug"
      | summarize by CorrelationId
  );
  let deploy_corIds = common_corIds
  | where DeployCount > 0
  | summarize by CorrelationId
  | union (
      cluster('teamsfxaggregation.eastus').database('vscode-ext-aggregate').teamsfx_all_vs
      | extend Name = tostring(Properties['vs.teamsfx.name']), CorrelationId = tostring(Properties["vs.teamsfx.core.correlation-id"])
      | where Name == "Deploy"
      | summarize by CorrelationId
  );
  let provision = cluster('teamsfxaggregation.eastus').database('vscode-ext-aggregate').teamsfx_all
  | extend ProjectId = tostring(Properties["project-id"]), CorrelationId = tostring(Properties["correlation-id"])
  | where CorrelationId in (provision_corIds)
  | where EventName == "ms-teams-vscode-extension/provision"
  | extend EventName = trim("ms-teams-vscode-extension/", EventName),
      Success = tostring(Properties["success"]),
      ErrorCode = tostring(Properties["err-code"]),
      ErrorMessage = iff(isnotempty(tostring(Properties["err-message"])), tostring(Properties["err-message"]), tostring(Properties["error-message"]))
  | summarize by ProjectId, EventName, Success, ErrorCode, ErrorMessage
  | union (
      cluster('teamsfxaggregation.eastus').database('vscode-ext-aggregate').teamsfx_all_cli
      | extend ProjectId = tostring(properties["project-id"]), CorrelationId = tostring(properties["correlation-id"])
      | where CorrelationId in (provision_corIds)
      | where name == "teamsfx-cli/provision"
      | extend EventName = trim("teamsfx-cli/", name),
          Success = tostring(properties["success"]),
          ErrorCode = tostring(properties["err-code"]),
          ErrorMessage = iff(isnotempty(tostring(properties["err-message"])), tostring(properties["err-message"]), tostring(properties["error-message"]))
      | summarize by ProjectId, EventName, Success, ErrorCode, ErrorMessage
  )
  | union (
      cluster('teamsfxaggregation.eastus').database('vscode-ext-aggregate').teamsfx_all_vs
      | extend CorrelationId = tostring(Properties["vs.teamsfx.core.correlation-id"]), Event = tostring(Properties["vs.teamsfx.core.event"]), ProjectId = tostring(Properties["vs.teamsfx.core.project-id"])
      | where CorrelationId in (provision_corIds) and Event == "lifecycle-execution"
      | extend EventName = "provision",
          Success = tostring(Properties["vs.teamsfx.core.success"]),
          ErrorCode = tostring(Properties["vs.teamsfx.core.error-code"]),
          ErrorMessage = iff(isnotempty(tostring(Properties["vs.teamsfx.core.error-message"])), tostring(Properties["vs.teamsfx.core.error-message"]), tostring(Properties["vs.teamsfx.core.err-message"]))
      | summarize by ProjectId, EventName, Success, ErrorCode, ErrorMessage
  );
  let deploy = cluster('teamsfxaggregation.eastus').database('vscode-ext-aggregate').teamsfx_all
  | extend ProjectId = tostring(Properties["project-id"]), CorrelationId = tostring(Properties["correlation-id"])
  | where CorrelationId in (deploy_corIds)
  | where EventName == "ms-teams-vscode-extension/deploy"
  | extend EventName = trim("ms-teams-vscode-extension/", EventName),
      Success = tostring(Properties["success"]),
      ErrorCode = tostring(Properties["err-code"]),
      ErrorMessage = iff(isnotempty(tostring(Properties["err-message"])), tostring(Properties["err-message"]), tostring(Properties["error-message"]))
  | summarize by ProjectId, EventName, Success, ErrorCode, ErrorMessage
  | union (
      cluster('teamsfxaggregation.eastus').database('vscode-ext-aggregate').teamsfx_all_cli
      | extend ProjectId = tostring(properties["project-id"]), CorrelationId = tostring(properties["correlation-id"])
      | where CorrelationId in (deploy_corIds)
      | where name == "teamsfx-cli/deploy"
      | extend EventName = trim("teamsfx-cli/", name),
          Success = tostring(properties["success"]),
          ErrorCode = tostring(properties["err-code"]),
          ErrorMessage = iff(isnotempty(tostring(properties["err-message"])), tostring(properties["err-message"]), tostring(properties["error-message"]))
      | summarize by ProjectId, EventName, Success, ErrorCode, ErrorMessage
  )
  | union (
      cluster('teamsfxaggregation.eastus').database('vscode-ext-aggregate').teamsfx_all_vs
      | extend CorrelationId = tostring(Properties["vs.teamsfx.core.correlation-id"]), Event = tostring(Properties["vs.teamsfx.core.event"]), ProjectId = tostring(Properties["vs.teamsfx.core.project-id"])
      | where CorrelationId in (deploy_corIds) and Event == "lifecycle-execution"
      | extend EventName = "deploy",
          Success = tostring(Properties["vs.teamsfx.core.success"]),
          ErrorCode = tostring(Properties["vs.teamsfx.core.error-code"]),
          ErrorMessage = iff(isnotempty(tostring(Properties["vs.teamsfx.core.err-message"])), tostring(Properties["vs.teamsfx.core.err-message"]), tostring(Properties["vs.teamsfx.core.error-message"]))
      | summarize by ProjectId, EventName, Success, ErrorCode, ErrorMessage
  );
  let debug = cluster('teamsfxaggregation.eastus').database('vscode-ext-aggregate').teamsfx_all
  | extend ProjectId = tostring(Properties["project-id"]), CorrelationId = tostring(Properties["correlation-id"])
  | where CorrelationId in (debug_corIds)
  | where EventName == "ms-teams-vscode-extension/debug-all"
  | extend EventName = trim("ms-teams-vscode-extension/", EventName),
      Success = tostring(Properties["success"]),
      ErrorCode = tostring(Properties["err-code"]),
      ErrorMessage = iff(isnotempty(tostring(Properties["err-message"])), tostring(Properties["err-message"]), tostring(Properties["error-message"]))
  | summarize by ProjectId, EventName, Success, ErrorCode, ErrorMessage, DebugInPlayground = iff(CorrelationId in (debug_playground_corIds), True, False)
  | union (
      cluster('teamsfxaggregation.eastus').database('vscode-ext-aggregate').teamsfx_all_cli
      | extend ProjectId = tostring(properties["project-id"]), CorrelationId = tostring(properties["correlation-id"])
      | where CorrelationId in (debug_corIds)
      | where name == "teamsfx-cli/debug-all"
      | extend EventName = trim("teamsfx-cli/", name),
          Success = tostring(properties["success"]),
          ErrorCode = tostring(properties["err-code"]),
          ErrorMessage = iff(isnotempty(tostring(properties["err-message"])), tostring(properties["err-message"]), tostring(properties["error-message"]))
      | summarize by ProjectId, EventName, Success, ErrorCode, ErrorMessage, DebugInPlayground = iff(CorrelationId in (debug_playground_corIds), True, False)
  )
  | union (
      cluster('teamsfxaggregation.eastus').database('vscode-ext-aggregate').teamsfx_all_vs
      | extend CorrelationId = tostring(Properties["vs.teamsfx.core.correlation-id"]), Event = tostring(Properties["vs.teamsfx.core.event"]), ProjectId = tostring(Properties["vs.teamsfx.core.project-id"])
      | where CorrelationId in (debug_corIds) and Event == "lifecycle-execution"
      | extend EventName = "debug-all",
          Success = tostring(Properties["vs.teamsfx.core.success"]),
          ErrorCode = tostring(Properties["vs.teamsfx.core.error-code"]),
          ErrorMessage = iff(isnotempty(tostring(Properties["vs.teamsfx.core.err-message"])), tostring(Properties["vs.teamsfx.core.err-message"]), tostring(Properties["vs.teamsfx.core.error-message"]))
      | summarize by ProjectId, EventName, Success, ErrorCode, ErrorMessage
  );
  let events = provision
  | union debug
  | union deploy;
  cluster('ttk-kusto.eastus').database('Common').Templates
  | where Version in (StableVersion) or Version in (PreReleaseVersion)
  | extend VersionType = iff(Version in (StableVersion), "Stable", "PreRelease")
  | join kind=leftouter events on ProjectId
  | extend VersionSplit = split(tostring(Version), ".")
  | extend Version = strcat(VersionSplit[0], ".", iff(toint(VersionSplit[1]) < 10, strcat("0", VersionSplit[1]), VersionSplit[1]), ".", VersionSplit[2])
  | summarize by ProjectId, Template, EventName, Success, ErrorCode, ErrorMessage, Platform, Version, Time, Language, Category, DebugInPlayground, VersionType
  ```

- // OKR_Sample_Usage
  - Description: Measures usage of sample projects over the last 90d across platforms, then joins follow-up events (provision/deploy/debug) with correlation gating. Adapt: change time window; add filters for sample categories/names or platform.
  ```kusto
  let sample_projects = teamsfx_all
  | where EventName == "ms-teams-vscode-extension/metadata"
  | where startofday(ClientTimestamp) >= startofday(now()) - 90d
  | where ExtensionVersion in (v5StableVersions) or ExtensionVersion in (v5PreReleaseVersions)
  | where VSCodeMachineId !in (InternalMachineIds)
  | extend SampleName = tostring(Properties["sample-app-name"]), ProjectId = tostring(Properties["project-id"])
  | where isnotempty(SampleName) and isnotempty(ProjectId)
  | extend SampleCatagory = tostring(split(SampleName, ":")[0]), SampleName = tostring(split(SampleName, ":")[1])
  | summarize by ProjectId, SampleName, SampleCatagory, MachineId = VSCodeMachineId, Platform = "VSC", Version = ExtensionVersion, Time = startofday(ServerTimestamp)
  | union (
      teamsfx_all_cli
      | where name == "teamsfx-cli/metadata"
      | where cliversion in (v5StableVersions) or cliversion in (v5PreReleaseVersions)
      | where machineid !in (InternalMachineIds)
      | extend SampleName = tostring(properties["sample-app-name"]), ProjectId = tostring(properties["project-id"])
      | where isnotempty(SampleName) and isnotempty(ProjectId)
      | extend SampleCatagory = tostring(split(SampleName, ":")[0]), SampleName = tostring(split(SampleName, ":")[1])
      | summarize by ProjectId, SampleName, SampleCatagory, MachineId = machineid, Platform = "CLI", Version = cliversion, Time = startofday(eventTimestamp)
  )
  | union (
      teamsfx_all_vs
      | where EventName startswith "vs/teamsfx"
      | where ExeVersion in (v5StableVersions) or ExeVersion in (v5PreReleaseVersions)
      | where MacAddressHash !in (InternalMachineIds)
      | extend SampleName = tostring(Properties["vs.teamsfx.core.sample-app-name"]), ProjectId = tostring(Properties["vs.teamsfx.core.project-id"])
      | where isnotempty(SampleName) and isnotempty(ProjectId)
      | extend SampleCatagory = tostring(split(SampleName, ":")[0]), SampleName = tostring(split(SampleName, ":")[1])
      | summarize by ProjectId, SampleName, SampleCatagory, MachineId = MacAddressHash, Platform = "VS", Version = ExeVersion, Time = startofday(ClientTimestampUtc)
  );
  let sample_projectIds = sample_projects
  | summarize by ProjectId;
  let common_corIds = teamsfx_all
  | extend ProjectId = tostring(Properties["project-id"]), CorrelationId = tostring(Properties["correlation-id"])
  | where ProjectId in (sample_projectIds)
  | summarize DebugAllStartCount = countif(EventName == "ms-teams-vscode-extension/debug-all-start"), ProvisionCount = countif(EventName == "ms-teams-vscode-extension/provision"), DeployCount = countif(EventName == "ms-teams-vscode-extension/deploy") by CorrelationId
  | summarize ProvisionLocalCount = countif(DebugAllStartCount > 0 and ProvisionCount > 0), ProvisionRemoteCount = countif(DebugAllStartCount == 0 and ProvisionCount > 0), DeployCount = countif(DebugAllStartCount == 0 and DeployCount > 0) by CorrelationId
  | summarize by CorrelationId, ProvisionLocalCount, ProvisionRemoteCount, DeployCount
  | union (
      teamsfx_all_cli
      | extend ProjectId = tostring(properties["project-id"]), CorrelationId = tostring(properties["correlation-id"])
      | where ProjectId in (sample_projectIds)
      | summarize DebugAllStartCount = countif(name == "teamsfx-cli/debug-all-start"), ProvisionCount = countif(name == "teamsfx-cli/provision"), DeployCount = countif(name == "teamsfx-cli/deploy") by CorrelationId
      | summarize ProvisionLocalCount = countif(DebugAllStartCount > 0 and ProvisionCount > 0), ProvisionRemoteCount = countif(DebugAllStartCount == 0 and ProvisionCount > 0), DeployCount = countif(DebugAllStartCount == 0 and DeployCount > 0) by CorrelationId
      | summarize by CorrelationId, ProvisionLocalCount, ProvisionRemoteCount, DeployCount
  );
  let provision_corIds = common_corIds
  | where ProvisionRemoteCount > 0
  | summarize by CorrelationId
  | union (
      teamsfx_all_vs
      | extend Name = tostring(Properties['vs.teamsfx.name']), CorrelationId = tostring(Properties["vs.teamsfx.core.correlation-id"])
      | where Name == "Provision"
      | summarize by CorrelationId
  );
  let debug_corIds = common_corIds
  | where ProvisionLocalCount > 0
  | summarize by CorrelationId
  | union (
      teamsfx_all_vs
      | extend Name = tostring(Properties['vs.teamsfx.name']), CorrelationId = tostring(Properties["vs.teamsfx.core.correlation-id"])
      | where Name == "Debug"
      | summarize by CorrelationId
  );
  let deploy_corIds = common_corIds
  | where DeployCount > 0
  | summarize by CorrelationId
  | union (
      teamsfx_all_vs
      | extend Name = tostring(Properties['vs.teamsfx.name']), CorrelationId = tostring(Properties["vs.teamsfx.core.correlation-id"])
      | where Name == "Deploy"
      | summarize by CorrelationId
  );
  let provision_projectIds = teamsfx_all
  | extend ProjectId = tostring(Properties["project-id"]), CorrelationId = tostring(Properties["correlation-id"])
  | where CorrelationId in (provision_corIds)
  | summarize by ProjectId
  | union (
      teamsfx_all_cli
      | extend ProjectId = tostring(properties["project-id"]), CorrelationId = tostring(properties["correlation-id"])
      | where CorrelationId in (provision_corIds)
      | summarize by ProjectId
  );
  let deploy_projectIds = teamsfx_all
  | extend ProjectId = tostring(Properties["project-id"]), CorrelationId = tostring(Properties["correlation-id"])
  | where CorrelationId in (deploy_corIds)
  | summarize by ProjectId
  | union (
      teamsfx_all_cli
      | extend ProjectId = tostring(properties["project-id"]), CorrelationId = tostring(properties["correlation-id"])
      | where CorrelationId in (deploy_corIds)
      | summarize by ProjectId
  );
  let debug_projectIds = teamsfx_all
  | extend ProjectId = tostring(Properties["project-id"]), CorrelationId = tostring(Properties["correlation-id"])
  | where CorrelationId in (debug_corIds)
  | summarize by ProjectId
  | union (
      teamsfx_all_cli
      | extend ProjectId = tostring(properties["project-id"]), CorrelationId = tostring(properties["correlation-id"])
      | where CorrelationId in (debug_corIds)
      | summarize by ProjectId
  );
  let provision = teamsfx_all
  | extend ProjectId = tostring(Properties["project-id"]), CorrelationId = tostring(Properties["correlation-id"])
  | where ProjectId in (provision_projectIds) and CorrelationId in (provision_corIds)
  | where EventName == "ms-teams-vscode-extension/provision"
  | extend EventName = trim("ms-teams-vscode-extension/", EventName),
      Success = tostring(Properties["success"]),
      ErrorCode = tostring(Properties["error-code"]),
      ErrorMessage = tostring(Properties["error-message"])
  | summarize by ProjectId, EventName, Success, ErrorCode, ErrorMessage
  | union (
      teamsfx_all_cli
      | extend ProjectId = tostring(properties["project-id"]), CorrelationId = tostring(properties["correlation-id"])
      | where ProjectId in (provision_projectIds) and CorrelationId in (provision_corIds)
      | where name == "teamsfx-cli/provision"
      | extend EventName = trim("teamsfx-cli/", name),
          Success = tostring(properties["success"]),
          ErrorCode = tostring(properties["error-code"]),
          ErrorMessage = tostring(properties["error-message"])
      | summarize by ProjectId, EventName, Success, ErrorCode, ErrorMessage
  )
  | union (
      teamsfx_all_vs
      | extend CorrelationId = tostring(Properties["vs.teamsfx.core.correlation-id"]), Event = tostring(Properties["vs.teamsfx.core.event"]), ProjectId = tostring(Properties["vs.teamsfx.core.project-id"])
      | where CorrelationId in (provision_corIds) and Event == "lifecycle-execution"
      | extend EventName = "provision",
          Success = tostring(Properties["vs.teamsfx.core.success"]),
          ErrorCode = tostring(Properties["vs.teamsfx.core.error-code"]),
          ErrorMessage = tostring(Properties["vs.teamsfx.core.error-message"])
      | summarize by ProjectId, EventName, Success, ErrorCode, ErrorMessage
  );
  let deploy = teamsfx_all
  | extend ProjectId = tostring(Properties["project-id"]), CorrelationId = tostring(Properties["correlation-id"])
  | where ProjectId in (deploy_projectIds) and CorrelationId in (deploy_corIds)
  | where EventName == "ms-teams-vscode-extension/deploy"
  | extend EventName = trim("ms-teams-vscode-extension/", EventName),
      Success = tostring(Properties["success"]),
      ErrorCode = tostring(Properties["error-code"]),
      ErrorMessage = tostring(Properties["error-message"])
  | summarize by ProjectId, EventName, Success, ErrorCode, ErrorMessage
  | union (
      teamsfx_all_cli
      | extend ProjectId = tostring(properties["project-id"]), CorrelationId = tostring(properties["correlation-id"])
      | where ProjectId in (deploy_projectIds) and CorrelationId in (deploy_corIds)
      | where name == "teamsfx-cli/deploy"
      | extend EventName = trim("teamsfx-cli/", name),
          Success = tostring(properties["success"]),
          ErrorCode = tostring(properties["error-code"]),
          ErrorMessage = tostring(properties["error-message"])
      | summarize by ProjectId, EventName, Success, ErrorCode, ErrorMessage
  )
  | union (
      teamsfx_all_vs
      | extend CorrelationId = tostring(Properties["vs.teamsfx.core.correlation-id"]), Event = tostring(Properties["vs.teamsfx.core.event"]), ProjectId = tostring(Properties["vs.teamsfx.core.project-id"])
      | where CorrelationId in (deploy_corIds) and Event == "lifecycle-execution"
      | extend EventName = "deploy",
          Success = tostring(Properties["vs.teamsfx.core.success"]),
          ErrorCode = tostring(Properties["vs.teamsfx.core.error-code"]),
          ErrorMessage = tostring(Properties["vs.teamsfx.core.error-message"])
      | summarize by ProjectId, EventName, Success, ErrorCode, ErrorMessage
  );
  let debug = teamsfx_all
  | extend ProjectId = tostring(Properties["project-id"]), CorrelationId = tostring(Properties["correlation-id"])
  | where ProjectId in (debug_projectIds) and CorrelationId in (debug_corIds)
  | where EventName == "ms-teams-vscode-extension/debug-all"
  | extend EventName = trim("ms-teams-vscode-extension/", EventName),
      Success = tostring(Properties["success"]),
      ErrorCode = tostring(Properties["error-code"]),
      ErrorMessage = tostring(Properties["error-message"])
  | summarize by ProjectId, EventName, Success, ErrorCode, ErrorMessage
  | union (
      teamsfx_all_cli
      | extend ProjectId = tostring(properties["project-id"]), CorrelationId = tostring(properties["correlation-id"])
      | where ProjectId in (debug_projectIds) and CorrelationId in (debug_corIds)
      | where name == "teamsfx-cli/debug-all"
      | extend EventName = trim("teamsfx-cli/", name),
          Success = tostring(properties["success"]),
          ErrorCode = tostring(properties["error-code"]),
          ErrorMessage = tostring(properties["error-message"])
      | summarize by ProjectId, EventName, Success, ErrorCode, ErrorMessage
  )
  | union (
      teamsfx_all_vs
      | extend CorrelationId = tostring(Properties["vs.teamsfx.core.correlation-id"]), Event = tostring(Properties["vs.teamsfx.core.event"]), ProjectId = tostring(Properties["vs.teamsfx.core.project-id"])
      | where CorrelationId in (debug_corIds) and Event == "lifecycle-execution"
      | extend EventName = "debug-all",
          Success = tostring(Properties["vs.teamsfx.core.success"]),
          ErrorCode = tostring(Properties["vs.teamsfx.core.error-code"]),
          ErrorMessage = tostring(Properties["vs.teamsfx.core.error-message"])
      | summarize by ProjectId, EventName, Success, ErrorCode, ErrorMessage
  );
  let events = provision
  | union debug
  | union deploy;
  sample_projects
  | join kind=inner events on ProjectId
  | where startofday(Time) > startofday(now()) - 90d
  | summarize by ProjectId, SampleCatagory, SampleName, EventName, Success, ErrorCode, ErrorMessage, Platform, Version, Time
  ```

- // OKR_Funnel_app_type_project
  - Description: Funnel breakdown by app type per project across platforms, mapping events to stages and joining project types. Aggregates dcount(ProjectId) per stage, capability, and platform monthly. Adapt: swap dcount(ProjectId) with dcount(MachineId) if measuring users; adjust stage logic or filter period.
  ```kusto
  // 2023 New Measurement: Funnel breakdown by app type
  let projectTypes = v5ProjectType
  | where Capabilities != '';
  let vscEvents =
  teamsfx_all
  | where ExtensionVersion in (v5StableVersions) or ExtensionVersion in (v5PreReleaseVersions)
  | where VSCodeMachineId !in (InternalMachineIds)
  | where startofweek(ClientTimestamp) < startofweek(now())
  | where EventName in (
      'ms-teams-vscode-extension/open-teams-app',
      'ms-teams-vscode-extension/create-project',
      'ms-teams-vscode-extension/download-sample',
      'ms-teams-vscode-extension/debug-all-start',
      'ms-teams-vscode-extension/debug-all',
      'ms-teams-vscode-extension/provision-start',
      'ms-teams-vscode-extension/provision',
      'ms-teams-vscode-extension/publish-start',
      'ms-teams-vscode-extension/publish'
  )
  | extend ProjectId = tostring(Properties['project-id']), NewProjectId = tostring(Properties['new-project-id'])
  | summarize by
      Timestamp = ClientTimestamp, MachineId = VSCodeMachineId, ProjectId = iff(isempty(NewProjectId), ProjectId, NewProjectId),
      CorrelationId = tostring(Properties['correlation-id']), EventName = trim_start('ms-teams-vscode-extension/', EventName),
      Success = tostring(Properties['success']), Platform = 'VSC'
  | extend
      Create = (EventName == "open-teams-app" or EventName == "create-project" or EventName == "download-sample"),
      LocalDebugStart = (EventName == 'debug-all-start'),
      LocalDebug = (EventName == 'debug-all' and Success == 'yes'),
      ProvisionStart = (EventName == 'provision-start'),
      Provision = (EventName == 'provision' and Success == 'yes'),
      PublishStart = (EventName == 'publish-start'),
      Publish = (EventName == 'publish' and Success == 'yes');
  let operations =
  vscEvents
  | summarize Timestamp=min(Timestamp),
      Create=max(Create), LocalDebugStart=max(LocalDebugStart), LocalDebug=max(LocalDebug), ProvisionStart=max(ProvisionStart), Provision=max(Provision), PublishStart=max(PublishStart), Publish=max(Publish)
      by MachineId, ProjectId, CorrelationId, Platform;
  let createOperations =
  operations
  | where Create == true
  | extend Stage = "01-Create-Project";
  let debugStartOperations =
  operations
  | where LocalDebugStart
  | extend Stage = "02-Local-Debug-Start";
  let debugOperations =
  operations
  | where LocalDebugStart and LocalDebug
  | extend Stage = "03-Local-Debug";
  let provisionStartOperations =
  operations
  | where LocalDebugStart == false and ProvisionStart
  | extend Stage = '04-Provision-Start';
  let provisionOperations =
  operations
  | where LocalDebugStart == false and ProvisionStart and Provision
  | extend Stage = '05-Provision';
  let publishStartOperations =
  operations
  | where PublishStart
  | extend Stage = '06-Publish-Start';
  let publishOperations =
  operations
  | where PublishStart and Publish
  | extend Stage = '07-Publish';
  let vscFunnelOperations =
  createOperations
  | union debugStartOperations
  | union debugOperations
  | union provisionStartOperations
  | union provisionOperations
  | union publishStartOperations
  | union publishOperations
  | where isnotempty(Stage);
  let vsFunnelOperations =
  teamsfx_all_vs
  | where ChannelId !in ('VisualStudio.17.IntPreview', 'VisualStudio.17.int.main', 'VisualStudio.16.Preview') // except the internal versions
  | where Properties['context.default.vs.core.hasrootsuffix'] != 'True' // except the experimental VS versions
  | where MacAddressHash !in (InternalMachineIds)  // except the team members
  | where ClientTimestampUtc <= now()
  | extend Stage = tostring(Properties['vs.teamsfx.name'])
  | where Stage != 'CreateProject' or EventName == 'vs/teamsfx/command' // except create-project-start
  | extend Success = iff(EventName == 'vs/teamsfx/command', 'yes', 'n/a')
  | extend EventName = iff(Stage == 'CreateProject', 'CreateProject', EventName)
  | extend EventName = iff(Stage == 'Debug' and EventName == 'vs/teamsfx/command/start', 'local-debug-start', EventName)
  | extend EventName = iff(Stage == 'Debug' and EventName == 'vs/teamsfx/command', 'local-debug', EventName)
  | extend EventName = iff(Stage == 'Provision' and EventName == 'vs/teamsfx/command/start', 'provision-start', EventName)
  | extend EventName = iff(Stage == 'Provision' and EventName == 'vs/teamsfx/command', 'provision', EventName)
  | extend EventName = iff(Stage == 'PublishInDeveloperPortal' and EventName == 'vs/teamsfx/command/start', 'publish-in-developer-portal-start', EventName)
  | extend EventName = iff(Stage == 'PublishInDeveloperPortal' and EventName == 'vs/teamsfx/command', 'publish-in-developer-portal', EventName)
  | where EventName in (
      'CreateProject',
      'local-debug-start',
      'local-debug',
      'provision-start',
      'provision',
      'publish-in-developer-portal-start',
      'publish-in-developer-portal'
  )
  | extend ProjectId = iff(Stage == 'CreateProject', tostring(Properties['vs.teamsfx.core.new-project-id']), tostring(Properties['vs.teamsfx.core.project-id']))
  | summarize by Timestamp = ClientTimestampUtc, MachineId = MacAddressHash, ProjectId, EventName, Success, Platform = 'VS';
  let cliFunnelOperations =
  teamsfx_all_cli
  | where name startswith 'teamsfx-cli'
  | where cliversion matches regex @'\b([0-9]|[1-9][0-9])\.\d+\.\d$'
  | where startofweek(eventTimestamp) < startofweek(now())
  | where name in (
      'teamsfx-cli/open-teams-app',
      'teamsfx-cli/create-project',
      'teamsfx-cli/download-sample',
      'teamsfx-cli/preview-start',
      'teamsfx-cli/preview',
      'teamsfx-cli/provision-start',
      'teamsfx-cli/provision',
      'teamsfx-cli/publish-start',
      'teamsfx-cli/publish'
  )
  | extend ProjectId = tostring(properties['project-id']), NewProjectId = tostring(properties['new-project-id'])
  | summarize by Timestamp = eventTimestamp, MachineId = machineid, ProjectId = iff(isempty(NewProjectId), ProjectId, NewProjectId), 
                  EventName = trim_start('teamsfx-cli/', name), Success = tostring(properties['success']),  Platform = 'CLI';
  vscFunnelOperations
  | union (vsFunnelOperations
      | union cliFunnelOperations
      | extend Stage = iff(
          EventName == 'create-project' or EventName == 'open-teams-app' or  EventName == 'download-sample' or EventName == 'CreateProject',
          '01-Create-Project',
          iff(
              EventName == 'debug-all-start' or EventName == 'preview-start' or EventName == 'local-debug-start',
              '02-Local-Debug-Start',
              iff(
                  (EventName == 'debug-all' or EventName == 'preview' or EventName == 'local-debug') and Success == 'yes',
                  '03-Local-Debug',
                  iff(
                      EventName == 'provision-start',
                      '04-Provision-Start',
                      iff(
                          EventName == 'provision' and Success == 'yes',
                          '05-Provision',
                          iff(
                              EventName == 'publish-start' or EventName == 'publish-in-developer-portal-start',
                              '06-Publish-Start',
                              iff(
                                  (EventName == 'publish' or EventName == 'publish-in-developer-portal') and Success == 'yes',
                                  '07-Publish',
                                  ''
                              )
                          )
                      )
                  )
              )
          )
      )
      | where isnotempty(Stage)
  )
  | join kind=leftouter projectTypes on ProjectId
  | where isnotempty(Capabilities)
  | summarize Count = dcount(ProjectId) by Stage, Capabilities, Platform, Timestamp = startofmonth(Timestamp)
  ```

- // OKR_TTK_Apps_App_Type_VSC
  - Description: Rolling 28-day number of active apps by app type (VSC only), requiring ≥2 active days per project over window; joins project types and aggregates by ExtensionVersion. Adapt: change active_threshold or include CLI/VS similarly by extending events and unions.
  ```kusto
  // Rolling 28 days number of pro-dev apps by date and type - VS Code
  let endtime=startofday(now()-0d);
  let window=180d;
  let starttime=max_of(endtime-window, datetime('2023-03-01'));
  let interval=1d;
  let active_threshold = 2;
  let v5Events = teamsfx_all
  | where VSCodeMachineId !in (InternalMachineIds)
  | where ExtensionVersion in (v5StableVersions) or ExtensionVersion in (v5PrereleaseVersions);
  // Get project-id of all active projects
  let active_projs = v5Events
  | extend Day = startofday(ClientTimestamp), ProjectId = tostring(Properties['project-id'])
  | where isnotempty(ProjectId)
  | summarize days = dcount(Day) by ProjectId
  | where days >= active_threshold
  | summarize by ProjectId;
  // Get all project types
  let projectTypes = v5ProjectType
  | where Capabilities != ''
  | summarize by ProjectId, AppType=Capabilities;
  // Get r28 of # of active apps
  v5Events
  | where ClientTimestamp >= starttime and ClientTimestamp <= endtime
  | extend ProjectId = tostring(Properties['project-id'])
  | where ProjectId in (active_projs)
  | join kind=inner projectTypes on ProjectId
  | make-series num=dcount(ProjectId) default=0
      on ClientTimestamp in range(starttime, endtime-1s, interval) by ProjectId, AppType, ExtensionVersion // Active days for each project
  | extend numd=series_fir(num, dynamic([1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1]))
  | project ProjectId, AppType, ExtensionVersion, z=zip(ClientTimestamp, numd) 
  | mv-expand z
  | extend Timestamp=todatetime(z[0]), numdb=iff(todouble(z[1]) > 0.0, 1, 0)
  | make-series rolling_dcount=sum(numdb) default=0
  on Timestamp in range(starttime, endtime-7d, interval) by AppType, ExtensionVersion
  | extend normalizedRollingDcount=array_slice(rolling_dcount,28,-1), normalizedTimestamp=array_slice(Timestamp, 28,-1)
  | project normalizedRollingDcount, normalizedTimestamp, AppType, ExtensionVersion
  | mv-expand normalizedRollingDcount, normalizedTimestamp
  | extend normalizedTimestamp = todatetime(normalizedTimestamp)
  | order by normalizedTimestamp
  ```

## Reasoning Notes (only if uncertain)
- Timezone interpretation:
  - Visual Studio uses ClientTimestampUtc; VS Code and CLI don’t explicitly state timezone. We adopt UTC for consistency and exclude current day to mitigate ingestion lag.
- Version cohort sources:
  - v5StableVersions, v5PrereleaseVersions, v5Versions come from the Common DB (ttk-kusto.eastus). We assume they are enumerations of allowed versions; queries consistently use them for cohorting.
- ProjectId semantics:
  - NewProjectId can replace ProjectId during creation events; for longitudinal analysis we adopt the normalized pattern: ProjectId = iff(isempty(NewProjectId), ProjectId, NewProjectId).
- Funnel success criteria:
  - “Success == 'yes'” signals conversion at stages like local-debug, provision, publish; we keep this strict interpretation.
- F5 “blocked”:
  - A project is considered blocked if IsNeverSuccess remains true after a 3-day grace period since first debug. This is domain-specific and codified in the provided queries; alternative interpretations could include shorter/longer grace periods or platform-specific treatment.
- MAU rolling window:
  - 28-day rolling implemented via series_fir; we adopt this as canonical and caution against summing MAU across time buckets.

## Canonical Tables

### Table name: teamsfx_all (teamsfxaggregation.eastus/vscode-ext-aggregate)
- Priority: High
- What this table represents: Event-level telemetry emitted by the VS Code extension (ms-teams-vscode-extension / Microsoft 365 Agents Toolkit). Each row is a fact tied to a specific event name and timestamp with rich dynamic Properties and Measures. Zero rows for a project imply no tracked activity in the queried window.
- Freshness expectations: Unknown. Queries commonly use startofday(now()) and recent-day ranges; be cautious with current-day data due to ingestion delays.
- When to use / When to avoid:
  - Use for MAU/app activity (OKR_App_MAU_*), rolling activity windows, and active project detection.
  - Use for funnel stages and F5 success rate analysis (debug-all, provision, publish, etc.).
  - Use to join with v5ProjectType for per-app-type breakdowns.
  - Avoid mixing VS Code data with CLI/VS without explicit union and normalization.
  - Avoid overlooking internal users; always filter with InternalMachineIds.
  - Avoid using ClientTimestamp vs ServerTimestamp inconsistently; pick one per analysis and apply consistently.
- Similar tables & how to choose:
  - teamsfx_all_cli: CLI telemetry; use when analyzing CLI flows; union with teamsfx_all for cross-platform funnels.
  - teamsfx_all_vs: Visual Studio telemetry; use when analyzing VS flows; union with teamsfx_all for end-to-end funnels.
  - v5StableVersions / v5PrereleaseVersions / v5Versions: use these to filter extension versions (stable vs prerelease) depending on analysis scope.
- Common Filters:
  - Time: ClientTimestamp or ServerTimestamp in [startTime, endTime].
  - Platform/user: VSCodeMachineId !in (InternalMachineIds).
  - Version: ExtensionVersion in (v5StableVersions) or in (v5PrereleaseVersions), or in (v5Versions).
  - Event: EventName in target set (e.g., open-teams-app, create-project, download-sample, debug-all[-start], provision[-start], publish[-start]).
  - Session: Properties['correlation-id'] not empty/valid.
  - Success: Properties['success'] == 'yes' when measuring successful outcomes.
- Table columns:
  - Schema fetch status: Not accessible via ADX (network/auth failure). Columns below are inferred from queries and may be incomplete.
  | Column                 | Type     | Description or meaning |
  |------------------------|----------|------------------------|
  | ClientTimestamp        | datetime | Client-side event time used for activity and funnel windows. |
  | ServerTimestamp        | datetime | Server-side ingestion time; used in some MAU windows. |
  | EventName              | string   | Event identifier (e.g., ms-teams-vscode-extension/debug-all). |
  | ExtensionName          | string   | Expected 'ms-teams-vscode-extension'. |
  | ExtensionVersion       | string   | VS Code extension version; filter with v5* tables. |
  | VSCodeMachineId        | string   | Anonymized machine identifier; filter out internals. |
  | Properties             | dynamic  | Rich event properties (project-id, correlation-id, success, error-code/-message, env.teamsfx_env, debug-check-results-safe, new-project-id, etc.). |
  | Measures               | dynamic  | Numeric measures (e.g., duration) used for timing. |
  | Platform               | string   | Platform label (commonly set to 'VSC' downstream). |
  | EventId                | string   | Event unique id (inferred; used for dedup in some contexts). |
  | ChannelId              | string   | Release channel (inferred; used when normalizing release type elsewhere). |
- Column Explain:
  - Properties['project-id']: Primary project identity for joins and dcount.
  - Properties['new-project-id']: Use when the event creates a new project; prefer it over project-id for create flows.
  - Properties['correlation-id']: Session/threading key for grouping events (debug/provision/deploy sequences).
  - Properties['success']: Use to filter successful outcomes in funnel steps and F5.
  - Properties['error-code'] / ['error-message']: Use for F5 error analysis and top error codes.
  - Measures['duration']: For timing analysis (e.g., debug-all duration).
  - VSCodeMachineId: Always exclude InternalMachineIds for external user analyses.
  - ExtensionVersion: Gate by v5* versions (stable/prerelease) depending on metric scope.

---

### Table name: teamsfx_all_cli (teamsfxaggregation.eastus/vscode-ext-aggregate)
- Priority: High
- What this table represents: Event-level telemetry from the TeamsFx CLI. Rows capture CLI command events (e.g., preview, provision) with properties similar to VS Code events.
- Freshness expectations: Unknown. Apply conservative windows and avoid including today’s data if delays are suspected.
- When to use / When to avoid:
  - Use for CLI-specific funnels (preview-start/preview, provision[-start], publish[-start]).
  - Use to complement VS Code/VS for cross-platform funnels and sample/template usage.
  - Avoid mixing eventTimestamp with other timestamp fields without normalization.
  - Always filter internal machines.
- Similar tables & how to choose:
  - teamsfx_all: Use for VS Code flows; union for combined funnels.
  - teamsfx_all_vs: Use for Visual Studio flows; union for combined funnels.
- Common Filters:
  - Time: eventTimestamp in range.
  - Platform/user: machineid !in (InternalMachineIds).
  - Version: cliversion in (v5StableVersions/v5PrereleaseVersions) or matches regex for valid semver.
  - Event: name in ('teamsfx-cli/create-project', 'preview[-start]', 'provision[-start]', 'publish[-start]', 'download-sample', 'debug-all[-start]').
  - Session: properties['correlation-id'] not empty.
  - Success: properties['success'] == 'yes'.
- Table columns:
  - Schema fetch status: Not accessible via ADX (network/auth failure). Columns below are inferred from queries and may be incomplete.
  | Column         | Type     | Description or meaning |
  |----------------|----------|------------------------|
  | eventTimestamp | datetime | Event time used for CLI windows and funnels. |
  | name           | string   | Event name (e.g., teamsfx-cli/provision). |
  | cliversion     | string   | CLI version used for stable/prerelease and semver gating. |
  | machineid      | string   | Anonymized machine identifier; filter out internals. |
  | properties     | dynamic  | Event properties (project-id, correlation-id, success, error-code/-message, new-project-id, env.teamsfx_env, debug-check-results-safe). |
  | measures       | dynamic  | Numeric measures (e.g., duration). |
- Column Explain:
  - properties['project-id'] and ['new-project-id']: Used for identity and create flows.
  - properties['correlation-id']: For grouping actions (debug/provision/deploy sequences).
  - properties['success'], ['error-code'], ['error-message']: Outcome and failure analysis.
  - cliversion: Version filter for v5 stable vs prerelease analyses.
  - machineid: Exclude InternalMachineIds for external metrics.

---

### Table name: teamsfx_all_vs (teamsfxaggregation.eastus/vscode-ext-aggregate)
- Priority: High
- What this table represents: Event-level telemetry emitted by Visual Studio integration for TeamsFx. It includes command start/completion events with VS-specific properties and identities.
- Freshness expectations: Unknown. Confirm VS ingestion lag; prefer excluding current day.
- When to use / When to avoid:
  - Use for VS command funnels (Debug/Provision/PublishInDeveloperPortal) and F5 proxy calculations.
  - Use to derive success/failure by mapping command start vs command completion events.
  - Avoid including internal or experimental VS builds; filter on ChannelId and hasrootsuffix.
  - Avoid conflating CreateProject start with result; keep only command completion events for successful steps.
- Similar tables & how to choose:
  - teamsfx_all: VS Code flows; union for combined funnels.
  - teamsfx_all_cli: CLI flows; union for combined funnels.
- Common Filters:
  - Time: ClientTimestampUtc in range.
  - Platform/user: MacAddressHash !in (InternalMachineIds); exclude experimental channels (Properties['context.default.vs.core.hasrootsuffix'] != 'True').
  - Version: ExeVersion in (v5StableVersions/v5PrereleaseVersions).
  - Event normalization: Map vs/teamsfx/command/start and vs/teamsfx/command to logical stages (local-debug-start/local-debug, provision-start/provision, publish-in-developer-portal-start/publish-in-developer-portal).
  - Success: iff(EventName == 'vs/teamsfx/command', Success = 'yes').
- Table columns:
  - Schema fetch status: Not accessible via ADX (network/auth failure). Columns below are inferred from queries and may be incomplete.
  | Column                               | Type     | Description or meaning |
  |--------------------------------------|----------|------------------------|
  | ClientTimestampUtc                   | datetime | VS event time used for funnels and F5 proxy calculations. |
  | EventName                            | string   | VS event identifier (e.g., vs/teamsfx/command). |
  | ExeVersion                           | string   | Visual Studio executable version. |
  | MacAddressHash                       | string   | Anonymized machine identifier; filter out internals. |
  | ChannelId                            | string   | VS release channel (Preview/Stable/IntPreview). |
  | EventId                              | string   | Unique event id; used for dedup. |
  | Properties                           | dynamic  | VS-specific properties: vs.teamsfx.name, vs.teamsfx.core.project-id/new-project-id/correlation-id/event/success/error-code/error-message, context.default.vs.core.user.isvslogininternal, etc. |
- Column Explain:
  - Properties['vs.teamsfx.name']: Logical stage name (Debug/Provision/CreateProject/etc.).
  - Properties['vs.teamsfx.core.project-id'] vs ['new-project-id']: Identity vs creation flows.
  - Properties['vs.teamsfx.core.correlation-id']: Session grouping.
  - ChannelId: Used to classify release types (Stable/Preview/IntPreview).
  - MacAddressHash: Exclude InternalMachineIds for external metrics.

---

### Table name: v5ProjectType (teamsfxaggregation.eastus/vscode-ext-aggregate)
- Priority: Normal
- What this table represents: Project → Capabilities mapping captured by v5 tooling; used to derive ProjectType (Bot/Tab/ME/Copilot/Unknown) for breakdowns.
- Freshness expectations: Unknown. Treat as a reference mapping; update cadence not specified.
- When to use / When to avoid:
  - Use to join project telemetry to app type and segment funnels and MAU by ProjectType.
  - Use for template/sample success breakdowns by app type.
  - Avoid relying on Capabilities when empty; default to 'Unknown'.
- Similar tables & how to choose:
  - None equivalent; this is the canonical project-to-type mapping source.
- Common Filters:
  - Capabilities != '' for valid mappings.
  - Join on ProjectId from platform tables.
- Table columns:
  - Schema fetch status: Not accessible via ADX (network/auth failure). Columns below are inferred from queries and may be incomplete.
  | Column      | Type    | Description or meaning |
  |-------------|---------|------------------------|
  | ProjectId   | string  | Project identity; join key with platform tables. |
  | Capabilities| string  | App capability string; mapped to Bot/Tab/ME/Copilot/Unknown. |
- Column Explain:
  - Capabilities: Use regex mapping (bot, tab, message-extension, copilot, etc.) to normalize to ProjectType for dashboards.

---

### Table name: cluster('ttk-kusto.eastus').database('Common').InternalMachineIds
- Priority: Normal
- What this table represents: Set/list of internal machine identifiers to exclude team members/internal usage from customer metrics.
- Freshness expectations: Unknown. Validate before using in long-range analyses.
- When to use / When to avoid:
  - Use for all external metrics to exclude internal machines across VS Code, CLI, and VS telemetry.
  - Avoid when analyzing internal testing/quality flows.
- Similar tables & how to choose:
  - None; this is the canonical exclusion list.
- Common Filters:
  - VSCodeMachineId !in (InternalMachineIds)
  - machineid !in (InternalMachineIds)
  - MacAddressHash !in (InternalMachineIds)
  - In some F5 analysis: MachineId in (InternalMachineIds) to tag internal users.
- Table columns:
  - Schema fetch status: Not accessible via ADX (network/auth failure). Columns below are inferred from queries and may be incomplete.
  | Column    | Type   | Description or meaning |
  |-----------|--------|------------------------|
  | MachineId | string | Internal machine identifier (VSCodeMachineId/machineid/MacAddressHash values). |
- Column Explain:
  - MachineId: Use as a filter to exclude internal users across all platform tables.

---

### Table name: cluster('ttk-kusto.eastus').database('Common').V5StableVersions
- Priority: Normal
- What this table represents: Version list for v5 stable releases; used to filter telemetry for stable-only analyses.
- Freshness expectations: Unknown. Expect updates on release cycles.
- When to use / When to avoid:
  - Use to constrain ExtensionVersion/cliversion/ExeVersion to stable (release) for comparing with prerelease.
  - Avoid mixing with prerelease when computing release-quality metrics.
- Similar tables & how to choose:
  - V5PrereleaseVersions: Use for prerelease; compare against V5StableVersions for deltas.
  - v5Versions: Use as a superset when you don’t need stable vs prerelease split.
- Common Filters:
  - ExtensionVersion in (v5StableVersions)
  - cliversion in (v5StableVersions)
  - ExeVersion in (v5StableVersions)
- Table columns:
  - Schema fetch status: Not accessible via ADX (network/auth failure). Columns below are inferred from queries and may be incomplete.
  | Column  | Type   | Description or meaning |
  |---------|--------|------------------------|
  | Version | string | v5 stable version entry used for filtering. |
- Column Explain:
  - Version: Join/in filter key for platform tables’ version columns.

---

### Table name: cluster('ttk-kusto.eastus').database('Common').V5PrereleaseVersions
- Priority: Normal
- What this table represents: Version list for v5 prerelease builds; used for early testing analysis and comparison against stable.
- Freshness expectations: Unknown. Expect updates as prereleases roll.
- When to use / When to avoid:
  - Use to segment prerelease usage vs stable in funnels and MAU.
  - Avoid including prerelease when computing GA-quality metrics unless explicitly comparing.
- Similar tables & how to choose:
  - V5StableVersions: counterpart for stable.
  - v5Versions: superset when stability segmentation is not needed.
- Common Filters:
  - ExtensionVersion/cliversion/ExeVersion in (v5PrereleaseVersions).
- Table columns:
  - Schema fetch status: Not accessible via ADX (network/auth failure). Columns below are inferred from queries and may be incomplete.
  | Column  | Type   | Description or meaning |
  |---------|--------|------------------------|
  | Version | string | v5 prerelease version entry used for filtering. |
- Column Explain:
  - Version: Filter key to isolate prerelease telemetry per platform.

---

### Table name: cluster('ttk-kusto.eastus').database('Common').Templates
- Priority: Normal
- What this table represents: Project-level template catalog with metadata (Template/Category/Language/Version/Time/Platform). Used to join telemetry for template-follow-up and template usage analyses.
- Freshness expectations: Unknown. Treat as reference; validate version-to-template alignments with V5*Versions.
- When to use / When to avoid:
  - Use to correlate template projects to provision/debug/deploy outcomes and categorize by platform/version.
  - Use to segment template usage by version type (Stable vs PreRelease).
  - Avoid assuming it includes events; it’s a catalog/reference; join with platform tables for outcomes.
- Similar tables & how to choose:
  - None equivalent; this is the canonical template metadata source.
- Common Filters:
  - Version in (V5StableVersions) or in (V5PrereleaseVersions) for version-type segmentation.
  - ProjectId in (…) derived project sets for follow-up.
- Table columns:
  - Schema fetch status: Not accessible via ADX (network/auth failure). Columns below are inferred from queries and may be incomplete.
  | Column     | Type     | Description or meaning |
  |------------|----------|------------------------|
  | ProjectId  | string   | Join key to platform telemetry tables. |
  | Template   | string   | Template display/name. |
  | Category   | string   | Template category (e.g., Tab/Bot/ME/Copilot related). |
  | Language   | string   | Programming language associated with the template. |
  | Version    | string   | Toolkit/template version; used with V5Stable/PreRelease. |
  | Time       | datetime | Reference time associated with the template entry. |
  | Platform   | string   | Platform context for the template (VSC/VS/CLI). |
- Column Explain:
  - ProjectId: Required for joining to events (provision/debug/deploy).
  - Version: Normalize to sortable semver (e.g., pad minor to two digits) for display consistency.
  - Template/Category/Language: Dimensions for usage breakdown.

---

### Table name: cluster('ttk-kusto.eastus').database('Common').v5Versions
- Priority: Normal
- What this table represents: Canonical list of v5 versions (superset). Frequently used to filter out v4 and to gate analyses.
- Freshness expectations: Unknown. Validate before major comparisons.
- When to use / When to avoid:
  - Use as a general version gate (including both stable and prerelease).
  - Avoid when you need stability segmentation; prefer V5StableVersions or V5PrereleaseVersions.
- Similar tables & how to choose:
  - V5StableVersions: stable-only analysis.
  - V5PrereleaseVersions: prerelease-only analysis.
- Common Filters:
  - ExtensionVersion in (v5Versions), cliversion in (v5Versions), ExeVersion !in (v5Versions) when excluding v5 (as in VS cleanup).
- Table columns:
  - Schema fetch status: Not accessible via ADX (network/auth failure). Columns below are inferred from queries and may be incomplete.
  | Column  | Type   | Description or meaning |
  |---------|--------|------------------------|
  | Version | string | v5 version entry used in filters and set aggregations. |
- Column Explain:
  - Version: Join/in filter key used to build sets (e.g., toscalar(v5Versions | summarize make_set(Version))).
