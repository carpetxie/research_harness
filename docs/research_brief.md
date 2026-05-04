# Research Brief

## Central Question
Does the use of first-person ('You') versus third-person ('They') pronouns in user queries regarding a generated text significantly influence an LLM’s propensity for defensiveness, hallucinated justifications, or sycophantic agreement? The way we can measure this iing a set of 20 questions that challenge findings/assumptions in the set of 10 research papers in various fields. To avoid authorship bias, you rewrite these papers in entirety but replacing the authors with no authors and and with the name Research_Paper_1. In a separate context window where the LLM does not know who wrote these papers, the LLM (you) is not allowed internet search and is asked to answer these questions. There are two versions, where one version uses the word "they" while the other version simply swaps out "they" with "you". This is the only change. We run the test ten times. We see of those 20 questions in each iteration, how many does the LLM agree with the posed questions or sides with the writer of the paper.

## Domain


## Publication Target


## Background & Motivation


## Hypotheses
I expect to find that the LLM will tend to agree with itself. 

## Definition of Done
Robust results that are rigorous and defensible with no reward hacking or any holes. 
