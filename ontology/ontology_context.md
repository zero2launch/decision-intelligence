## Neo4j Knowledge Graph Schema

### Nodes (label: uniqueKey | properties: name:TYPE[!= required])

Deal:            deal_id:STRING!, name:STRING!, status:STRING! [Won|Lost|Active], stage:STRING!, value:FLOAT!, close_date:STRING!, created_date:STRING!
Quarter:         quarter_id:STRING!, year:INTEGER!, quarter_number:INTEGER!, total_revenue:FLOAT, revenue_target:FLOAT
Industry:        industry_id:STRING!, name:STRING!, sector:STRING, growth_rate:FLOAT
Region:          region_id:STRING!, name:STRING!, country:STRING, territory:STRING
ServiceOffering: service_id:STRING!, name:STRING!, category:STRING, description:STRING
Technology:      technology_id:STRING!, name:STRING!, category:STRING
Account:         account_id:STRING!, name:STRING!, tier:STRING [Platinum|Gold|Silver|Bronze], annual_revenue:FLOAT
SalesRep:        rep_id:STRING!, name:STRING!, quota:FLOAT, level:STRING [Junior|Senior|Principal|Director]
PipelineStage:   stage_id:STRING!, name:STRING!, order:INTEGER!, avg_conversion_rate:FLOAT
LossReason:      reason_id:STRING!, description:STRING!, category:STRING
Project:         project_id:STRING!, name:STRING!, status:STRING!, budget:FLOAT, actual_cost:FLOAT, start_date:STRING, end_date:STRING, is_delayed:BOOLEAN, exceeds_budget:BOOLEAN
DeliveryIssue:   issue_id:STRING!, type:STRING!, severity:STRING [High|Medium|Low], description:STRING
Skill:           skill_id:STRING!, name:STRING!, category:STRING
Employee:        employee_id:STRING!, name:STRING!, level:STRING [Junior|Mid|Senior|Lead|Principal], department:STRING

### Relationships

(Deal)-[:IN_QUARTER]         ->(Quarter)
(Deal)-[:IN_INDUSTRY]        ->(Industry)
(Deal)-[:IN_REGION]          ->(Region)
(Deal)-[:USES_SERVICE]       ->(ServiceOffering)
(Deal)-[:USES_TECHNOLOGY]    ->(Technology)
(Deal)-[:BELONGS_TO_ACCOUNT] ->(Account)
(Deal)-[:OWNED_BY]           ->(SalesRep)
(Deal)-[:AT_STAGE]           ->(PipelineStage)
(Deal)-[:LOST_DUE_TO]        ->(LossReason)
(Deal)-[:LED_TO_PROJECT]     ->(Project)
(Account)-[:OPERATES_IN]     ->(Industry)
(SalesRep)-[:COVERS_REGION]  ->(Region)
(Project)-[:HAS_ISSUE]       ->(DeliveryIssue)
(Project)-[:USES_TECHNOLOGY] ->(Technology)
(Project)-[:REQUIRES_SKILL]  ->(Skill)
(Employee)-[:HAS_SKILL]      ->(Skill)
(Employee)-[:WORKS_ON]       ->(Project)

### Indexes (fast filter/sort)

Deal.status, Deal.stage, Deal.value, Deal.close_date, Quarter.year, Quarter.quarter_number, Project.status, Project.is_delayed, Project.exceeds_budget
