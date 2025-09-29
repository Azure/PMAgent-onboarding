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
    - Paste the queries in markdown, and update each query **with proper comments** to the PM Agent understand them. 
        - You could also use the following prompts to ask AI to help you clean up the queries. 

    ```markdown
    Translate the following markdown content with Power BI queries into KQL queries. 
    - Keeping original `// comments` above each query.
    - Removing the `let Source = AzureDataExplorer.Contents(...) in Source` Power Query wrapping, leaving clean KQL.
    - For the table in each query, using KQL syntax, like cluster("cluster instance").database("db").table
    - Replacing #(lf) with proper line returns.
    - Translate all queries into a .kql file. 

    <Paste your queries from Power BI here.>
    ```
    
> [!IMPORTANT] 
> The comments should explain the main purpose and usage of each query to help the PM Agent understand them.

- **Option 3: Download documentation from product wiki in markdown**

- **Option 4: Queries from Lens Jobs in markdown**

    - If a data pipeline exists (e.g., Lens Jobs) from raw telemetry to aggregated telemetry, also include the queries used in this pipeline. These queries are important for helping the PM Agent build knowledge and enable deep-dive ad-hoc analysis, connecting signals in aggregated telemetry to insights in raw telemetry. 
        - Copy the queries from Lens Jobs **with proper comments** in markdown. Otherwise, if you are using Kusto functions for the pipeline, you could also use following command to get the queries.

    
> [!IMPORTANT] 
> The comments should explain the main purpose and usage of each query to help the PM Agent understand them.

- **Option 5: KQL functions from ADX**

    - Sometimes, your dashboard or pipeline may use pre-defined KQL functions. These functions are alos important for helping the PM Agent build knowledge and connect telemetry in data tables to aggregated telemetry in dashboard or pipeline.

        - Go to `Azure Data Explore`, and navigate to your database with user-defined functions.
        - Run the following commnd. 

        ```kql 
        .show functions
        ```

        - Select `Export` -> `Export to CSV` to download the result. 
        - Paste the fcuntions with KQL syntax in markdown, and update each function **with proper comments** to the PM Agent understand them. 
            - You could also use the following prompts to ask AI to help you clean up the functions. 

        ```markdown
        Translate the csv content from KQL .show functions command into KQL queries. 
        - Using the DocString, Folder and Name to generate comment for each function. 
        - Using the Name, Parameters and Body to build the function in KQL syntax. 
        - Translate all functions.

        <upload your csv file or paste the content of csv file here.>
        ```

> [!IMPORTANT] 
> The comments should explain the main purpose and usage of each query to help the PM Agent understand them.

## Submit the reference information 

- `Add a comment` in this issue to share the reference information helping PM Agent to build product specific knowledge. 
    - For each referenced resource, describe it following the **required format**.
    - If multiple resources are involved, combine them into one comment instead of creating separate comments.

### **Formatting of referenced resource**

```markdown
## Product Information 

- Product Name: 
- Product Description: 

> [!TIP]
> You could also add more information to help PM agent understand your product.

## Terminology

> [!TIP]
> Using [List](https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax#lists) to define Product-specific Terminology.

## [Product Resource Name]

> [!TIP]
> - The product resource name should be clear and product specific, e.g., 'Dashboard for product XYZ' instead of 'Dashboard'.
> - You could also add description here to describe the relationship between this resource to other resources. 

### **Product Resource Type**

- [ ] ADX Dahsboard (json content)
- [ ] Power BI dashboard (queries in markdown)
- [ ] Lens Explorer (queries in markdown) 
- [ ] KQL Functions (functions in markdown) 
- [ ] Documentation (markdown from wiki)

### **Product Resource**

> [!TIP]
> Using [Fenced Code Block](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/creating-and-highlighting-code-blocks#fenced-code-blocks) to define the reference from existing resources, e.g., content of ADX dashboard in json, KQL queries in markdown, etc.

----

> [!TIP]
> Repeat the `Product Resource Name` section with `horizontal line` (---) for each resource. 

```



