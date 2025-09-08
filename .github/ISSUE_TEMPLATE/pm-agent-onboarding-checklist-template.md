---
name: PM Agent Onboarding Checklist Template
about: Template of PM agent onboarding checklist
title: "Product Onboarding Checklist: <Offical Product Name> "
labels: 'onboarding'
assignees: ''

---

# PM Agent Onboarding Checklist 

## Authentication and Authorization Setup

- [ ] Allow PM agent to access your product telemetry
  - If your ADX is in MSFT tenant (72f988bf-86f1-41af-91ab-2d7cd011db47), run the follow command in ADX 

    ```kusto
    .add database Samples viewers ('aadapp=2edc5bb8-8658-4c23-b808-b7fda3be7428')
    ```

  - Otherwise, if your ADX is NOT in MSFT tenant
    - [Allow cross-tenant](https://learn.microsoft.com/en-us/azure/data-explorer/cross-tenant-query-and-commands?tabs=portal)
    - run the follow command in ADX 

     ```kusto
    .add database Samples viewers ('aadapp=2edc5bb8-8658-4c23-b808-b7fda3be7428;72f988bf-86f1-41af-91ab-2d7cd011db47')

- [ ] Share security groups with the PM Agent team to manage which teams can access your product telemetry through PM Agent.

## Setup PM Agent in Microsoft Teams

- [ ] Setup PM Agent in Microsoft Teams 

  - Download the app package from [PM Agent Dogfood and Support](https://microsoftapc-my.sharepoint.com/:u:/g/personal/yajin1_microsoft_com/EX5WJtjlusJNpaypoo0S-98BUxoHY_ETRbZYZl4q6aiMOA?e=NA2Acp).
  - Launch Microsoft Teams.
  - Go to Apps -> Managed your apps -> Upload an app -> Upload a custom app.

    ![Install PM Agent Teams Bot by uploading a custom app - Step 1](https://raw.githubusercontent.com/Azure/PMAgent-onboarding/main/docs/resources/Install_PM_Agent_01.png "Upload App Package")

  - Choose the app package and install it.

    ![Install PM Agent Teams Bot by uploading a custom app - Step 2](https://raw.githubusercontent.com/Azure/PMAgent-onboarding/main/docs/resources/Install_PM_Agent_02.png "Install PM Agent")

  - Launch PM agent in Microsoft Teams. 

    ![Launch PM Agent in Microsoft Teams](https://raw.githubusercontent.com/Azure/PMAgent-onboarding/main/docs/resources/Launch_PM_Agent.png "Launch PM Agent")

## Build Product (or Domain) Knowledge

- [ ] Prepare your existing quries as reference to build product knowledge 

  - Option 1: Download Azure Data Explore dashboard as json file. 

    - Go to dashboard in Azure Data Explorer. 
    - Click `File` and then choose `Download dashboard to file` to download the dashboard as json file.

    ![Download ADE dashboard](https://raw.githubusercontent.com/Azure/PMAgent-onboarding/main/docs/resources/Download_ADE_Dashboard.png "Download Azure Data Explore Dashboard")

  - Option 2: Download queries from Power BI dashboard.

    - Go to the Power BI dashboard online.
    - Click `File` and then choose `Download this file`. 
    - Choose `A copy of your report and data (.pbix)` option and download dshabord. 
    - Open the dashboard file (.pbix) in Power BI Desktop. 
    - Click `Transform Data`.
    - Select all queries in the `Queries` pane and `Ctrl+C` to copy them. 
    - Paste the queries with comment in a markdown file.

  - Option 3: Download documentation from product wiki as markdown file.

- [ ] Create a [GitHub issue](https://github.com/Azure/PMAgent-onboarding/issues/new?template=pm-agent-queries-template.md) to upload the resources you prepared, and copy the URL of this issue. 

- [ ] Go to PM agent and ask PM agent to generate product knowledge with the URL of GitHb issue for product resources. PM agent will help you create a PR for initial product knowledge.

> onboard new product: find details about product history queries from <GitHub issue URL or link to specific comment in GitHub issue>

- [ ] Complete all **[TODO]Data_Engineer** actions in the PR, and then submit PR. 

- [ ] Continue opimizing your product knowledge with PRs in future. 