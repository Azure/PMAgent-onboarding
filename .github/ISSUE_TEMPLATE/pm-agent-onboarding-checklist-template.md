---
name: PM Agent Onboarding Checklist Template
about: Template of PM agent onboarding checklist
title: "[Product Onboarding] "
labels: ''
assignees: ''

---

# PM Agent Onboarding Checklist 

## Authentication and Authorization Setup

- [] Allow PM agent to access your product telemetry
  - If your ADX is in MSFT tenant (72f988bf-86f1-41af-91ab-2d7cd011db47), run the follow command in ADX 

    ```kusto
    .add database Samples viewers ('aadapp=2edc5bb8-8658-4c23-b808-b7fda3be7428')
    ```

  - Otherwise, if your ADX is NOT in MSFT tenant
    - [Allow cross-tenant](https://learn.microsoft.com/en-us/azure/data-explorer/cross-tenant-query-and-commands?tabs=portal)
    - run the follow command in ADX 

     ```kusto
    .add database Samples viewers ('aadapp=2edc5bb8-8658-4c23-b808-b7fda3be7428;72f988bf-86f1-41af-91ab-2d7cd011db47')

- [] Share the security groups with PM agent team to manage the teams which could access your product telemetires via PM agent

## Build Product (or Domain) Knowledge
