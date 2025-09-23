---
name: Prdouct Knowledge Resources
about: Describe the product resources to build knowledge base with PM Agent
title: "Onboard Product: <Offical Product Name>"
labels: 'onboarding'
assignees: ''

---

# Build product-specific knowledge with PM Agent

## How to get reference information from existing resources

- **Option 1: Download Azure Data Explore dashboard as json file**

    - Go to dashboard in Azure Data Explorer. 
    - Click `File` and then choose `Download dashboard to file` to download the dashboard as json file.

![Download ADE dashboard](https://raw.githubusercontent.com/Azure/PMAgent-onboarding/main/docs/resources/Download_ADE_Dashboard.png "Download Azure Data Explore Dashboard")

- **Option 2: Download queries from Power BI dashboard**

    - Go to the Power BI dashboard online.
    - Click `File` and then choose `Download this file`. 
    - Choose `A copy of your report and data (.pbix)` option and download dshabord. 
    - Open the dashboard file (.pbix) in Power BI Desktop. 
    - Click `Transform Data`.
    - Select all queries in the `Queries` pane and `Ctrl+C` to copy them. 
    - Paste the queries **with proper comments** in markdown. 
    
> [!IMPORTANT] 
> The comments should explain the main purpose and usage of each query to help the PM Agent understand them.

- **Option 3: Download documentation from product wiki in markdown**

- **Option 4: Queries from Lens Jobs in markdown**

If a data pipeline exists (e.g., Lens Jobs) from raw telemetry to aggregated telemetry, also include the queries used in this pipeline. These queries are important for helping the PM Agent build knowledge and enable deep-dive ad-hoc analysis, connecting signals in aggregated telemetry to insights in raw telemetry. 

    - Copy the queries from Lens Jobs **with proper comments** in markdown. Otherwise, if you are using Kusto functions for the pipeline, you could also use following command to get the queries. 
    
> [!IMPORTANT] 
> The comments should explain the main purpose and usage of each query to help the PM Agent understand them.

## Submit the reference information 

- `Add a comment` in this issue to share the reference information helping PM Agent to build product specific knowledge. 
    - For each referenced resource, describe it following the **required format**.
    - If multiple resources are involved, combine them into one comment instead of creating separate comments.

### **Formatting of referenced resource**

> ## [Product Resource Name]
> 
> ### **Product Resource Type**
> 
> - [ ] ADX Dahsboard (json content)
> - [ ] Power BI dashboard (queries in markdown)
> - [ ] Lens Explorer (queries in markdown) 
> - [ ] Documentation (markdown from wiki)
> 
> ### **Product Resource**
> 
> ```
> [Reference from existing resource, e.g., content of ADX dashboard in json, KQL queries in markdown, etc.]
> ```
> 
> ----



