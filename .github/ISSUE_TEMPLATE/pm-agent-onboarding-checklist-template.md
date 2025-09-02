---
name: PM Agent Onboarding Checklist Template
about: Template of PM agent onboarding checklist
title: "[Product Onboarding] "
labels: ''
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

    ![Install PM Agent Teams Bot by uploading a custom app - Step 1](https://github.com/Azure/PMAgent-onboarding/blob/main/docs/resources/Install_PM_Agent_01.png "Upload App Package")


  - Choose the app package and install it.

    ![Install PM Agent Teams Bot by uploading a custom app - Step 2](https://github.com/Azure/PMAgent-onboarding/blob/main/docs/resources/Install_PM_Agent_02.png "Install PM Agent")

  - Launch PM agent in Microsoft Teams. 

    ![Launch PM Agent in Microsoft Teams](https://github.com/Azure/PMAgent-onboarding/blob/main/docs/resources/Launch_PM_Agent.png "Launch PM Agent")

## Build Product (or Domain) Knowledge

- [ ] Build initial product-specific knowledge 
