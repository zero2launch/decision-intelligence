## IT Service/Consulting Revenue Intelligence Tool 

### Setup 

```bash

  uv init --name decision-intelligence 
  uv venv 
  uv add fastapi uvicorn neo4j openai 
  uv run uvicorn src.main:app --reload # run backend 
  uv run python frontend/main.py # run frontend

```

### Questions

## Competency Questions (CQs) for Ontology Design

1. Why did revenue drop this quarter?
2. Which industries contribute the most revenue?
3. Which regions are underperforming?
4. Which service offerings generate the highest revenue?
5. Which technologies generate the highest revenue?
6. What is the expected revenue next quarter?
7. Which accounts contribute most to revenue?
8. Which industries are growing fastest?
9. Why are deals being lost?
10. Which stage has the highest pipeline leakage?
11. Why has the win rate decreased?
12. Which sales reps are underperforming?
13. What factors correlate with successful deals?
14. Which technologies have the highest win rate?
15. What are the top reasons for deal loss?
16. Are delivery issues causing revenue loss?
17. Which projects are delayed?
18. Which projects exceed budget?
19. Are skill shortages affecting deal wins?
20. Which technologies are associated with project delays?