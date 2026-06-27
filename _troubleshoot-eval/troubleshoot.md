# planning to do some generator / retrive / judge adjustments 
if I start changing system prompts, how can that be refleced in the telemetry.
right now it just persists the sha. But my /home/jhigaki/projects/rag-bench-analytics/README.md repo will do analysis queries around dimensions. One of them can be system prompt version along with system prompt improvement

# entity extraction
whow this is done today and would another LLM component benefit from doing entity extraction as an intermediare between generator <--> retrieveer?

# token saving on format
what if the retriever, instead of providing sparql it hands off json-ld ?
Would it be good?
now that triples contain very few metadata could be right, after metadata adding, maybe not?

# judging gt mechanism on negative unanswered
"question": "Which diseases does Testolactone treat?",
  "ground_truth": [],
    "predicted": "None",
      "judged": true,
  "passed": true,
  "score": 1,
  "verdict": "correctly refused / asserted none",

But this could mean that Testolactone does not treat any disease. Is this CWA. meaning that if gt is empty, there is no sufficient information
System prompt should assume that RAG is all knowledge, anything that isnt there, is negative

# refusal vs good score
ingestion_sample/20260615T200851-graph_sparqlgen-anthropic.jsonl 
  "question_id": "05_aggregative__count_of_side_effects_caused_by_compound__00",
refused to answer but did include a correct: n=184  reference that was scored well by the judge.
Should the judge had interpreted as refusal and this would've been an incorrect refusal of the generator? 
the retriever did provide the right context

#refusal vs good score
ingestion_sample/20260615T200851-graph_sparqlgen-anthropic.jsonl 
  "question_id": "06_set_intersection__shared_pathways_of_two_genes__00",
the answer is refusal 
it wasnt interpreted as refusal "judged": true,
  "passed": false,
  "score": 0.7499999999999999,
  "verdict": "set F1=0.75 (recall 3/3, 2 extra)",
  "judge_details": {
    "expected_count": 3,
    "found_count": 3,
    "missing": [],
    "precision": 0.6,
    "recall": 1,
    "f1": 0.75,
    "extra": [
      "I would need information about the pathway participation of both HMMR and NUP155.",
      "None"
    ],

and the restate of HMMR and NUP155 (proteins from quesiton) is interpreted as additional answer items, thus extra=2
why extra=2 is not metadata in the judge payload. Should it be?

# Retriever provided answer Generator didnt use

Gruont Truth reads
```json
{
  "question_id": "07_set_difference__pathways_in_one_gene_excluding_another__00",
  "type_id": "07_set_difference",
  "template_id": "pathways_in_one_gene_excluding_another",
  "question": "Which pathways does FSTL3 participate in that DUSP3 does not?",
  "scoring": "set_match",
  "answer_var": "pathwayLabel",
  "ground_truth": [
    "Antagonism of Activin by Follistatin",
    "Signaling by Activin"
  ],
  "ground_truth_query": "PREFIX hetio: <https://het.io/schema/>
PREFIX ncbigene: <https://identifiers.org/ncbigene/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?pathway ?pathwayLabel WHERE {
  VALUES ?geneA { <https://identifiers.org/ncbigene/10272> }
  VALUES ?geneB { <https://identifiers.org/ncbigene/1845> }
  ?geneA hetio:participates ?pathway .
  ?pathway a hetio:Pathway ;
           rdfs:label ?pathwayLabel .
  FILTER NOT EXISTS { ?geneB hetio:participates ?pathway . }
}
ORDER BY ?pathwayLabel",
  "seeds": [
    {
      "bind_var": "geneA",
      "label": "FSTL3",
      "uri": "https://identifiers.org/ncbigene/10272"
    },
    {
      "bind_var": "geneB",
      "label": "DUSP3",
      "uri": "https://identifiers.org/ncbigene/1845"
    }
  ],
  "sampling_seed": "20260605:pathways_in_one_gene_excluding_another"
}
```

in `"run_id": "20260615T200851-graph_sparqlgen-anthropic"`


this was scored

```json
{
  "question_id": "07_set_difference__pathways_in_one_gene_excluding_another__00",
  "type_id": "07_set_difference",
  "scoring": "set_match",
  "question": "Which pathways does FSTL3 participate in that DUSP3 does not?",
  "ground_truth": [
    "Antagonism of Activin by Follistatin",
    "Signaling by Activin"
  ],
  "retriever": "graph_sparqlgen",
  "generator_provider": "anthropic",
  "generator_model": "claude-haiku-4-5",
  "predicted": "I cannot determine which pathways FSTL3 participates in that DUSP3 does not based solely on the provided context. The context only lists two pathways related to Activin signaling but does not specify which proteins participate in each pathway.

To answer this question accurately, I would need information about:
1. All pathways that FSTL3 participates in
2. All pathways that DUSP3 participates in
3. A comparison of these two lists

None",
  "generator_model_resolved": "claude-haiku-4-5-20251001",
  "generator_temperature": 0,
  "input_tokens": 246,
  "output_tokens": 113,
  "cache_read_input_tokens": 0,
  "cache_creation_input_tokens": 0,
  "context_tokens_proxy": 36,
  "num_sources": 2,
  "retrieval_latency_ms": 1782.7,
  "generation_latency_ms": 1465.3,
  "traversal_info": {
    "mechanism": "sparqlgen",
    "writer_model": "claude-haiku-4-5-20251001",
    "writer_temperature": 0,
    "writer_input_tokens": 577,
    "writer_output_tokens": 172,
    "endpoint": "http://localhost:7200/repositories/hetionet",
    "sparql_generated": "PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?pathway ?pathwayLabel
WHERE {
  ?fstl3 rdfs:label \"FSTL3\" .
  ?dusp3 rdfs:label \"DUSP3\" .
  
  ?fstl3 hetio:participates ?pathway .
  ?pathway a hetio:Pathway .
  ?pathway rdfs:label ?pathwayLabel .
  
  FILTER NOT EXISTS {
    ?dusp3 hetio:participates ?pathway .
  }
}",
    "writer_reply_raw": "```sparql
PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?pathway ?pathwayLabel
WHERE {
  ?fstl3 rdfs:label \"FSTL3\" .
  ?dusp3 rdfs:label \"DUSP3\" .
  
  ?fstl3 hetio:participates ?pathway .
  ?pathway a hetio:Pathway .
  ?pathway rdfs:label ?pathwayLabel .
  
  FILTER NOT EXISTS {
    ?dusp3 hetio:participates ?pathway .
  }
}
```",
    "sparql": "PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?pathway ?pathwayLabel
WHERE {
  ?fstl3 rdfs:label \"FSTL3\" .
  ?dusp3 rdfs:label \"DUSP3\" .
  
  ?fstl3 hetio:participates ?pathway .
  ?pathway a hetio:Pathway .
  ?pathway rdfs:label ?pathwayLabel .
  
  FILTER NOT EXISTS {
    ?dusp3 hetio:participates ?pathway .
  }
}
LIMIT 200",
    "sparql_valid": true,
    "num_rows": 2,
    "context_tokenizer": "wordpunct-v1"
  },
  "judged": true,
  "passed": false,
  "score": 0,
  "verdict": "set F1=0.00 (recall 0/2, 5 extra)",
  "judge_details": {
    "expected_count": 2,
    "found_count": 0,
    "missing": [
      "Antagonism of Activin by Follistatin",
      "Signaling by Activin"
    ],
    "precision": 0,
    "recall": 0,
    "f1": 0,
    "extra": [
      "I cannot determine which pathways FSTL3 participates in that DUSP3 does not based solely on the provided context. The context only lists two pathways related to Activin signaling but does not specify which proteins participate in each pathway.",
      "All pathways that FSTL3 participates in",
      "All pathways that DUSP3 participates in",
      "A comparison of these two lists",
      "None"
    ],
    "basis": "set"
  }
}
```

There generated sparql already contained the filtered pathways
The generator didn't trust it 

# Retriever did well generator didnt get

question from gt

```json
{
  "question_id": "02_1hop_factoid__genes_expressed_in_anatomy__01",
  "type_id": "02_1hop_factoid",
  "template_id": "genes_expressed_in_anatomy",
  "question": "Which genes are expressed in ankle joint?",
  "scoring": "set_match",
  "answer_var": "geneLabel",
  "ground_truth": [
    "CFL1",
    "SMU1"
  ],
  "ground_truth_query": "PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX uberon: <http://purl.obolibrary.org/obo/UBERON_>

SELECT ?gene ?geneLabel WHERE {
  VALUES ?anatomy { <http://purl.obolibrary.org/obo/UBERON_0001488> }
  ?anatomy hetio:expresses ?gene .
  ?gene rdfs:label ?geneLabel .
}
ORDER BY ?geneLabel",
  "seeds": [
    {
      "bind_var": "anatomy",
      "label": "ankle joint",
      "uri": "http://purl.obolibrary.org/obo/UBERON_0001488"
    }
  ],
  "sampling_seed": "20260605:genes_expressed_in_anatomy"
}
```

generator got it wrong
```json
{
  "question_id": "02_1hop_factoid__genes_expressed_in_anatomy__01",
  "type_id": "02_1hop_factoid",
  "scoring": "set_match",
  "question": "Which genes are expressed in ankle joint?",
  "ground_truth": [
    "CFL1",
    "SMU1"
  ],
  "retriever": "graph_sparqlgen",
  "generator_provider": "anthropic",
  "generator_model": "claude-haiku-4-5",
  "predicted": "None",
  "generator_model_resolved": "claude-haiku-4-5-20251001",
  "generator_temperature": 0,
  "input_tokens": 220,
  "output_tokens": 4,
  "cache_read_input_tokens": 0,
  "cache_creation_input_tokens": 0,
  "context_tokens_proxy": 30,
  "num_sources": 2,
  "retrieval_latency_ms": 1180.9,
  "generation_latency_ms": 658.7,
  "traversal_info": {
    "mechanism": "sparqlgen",
    "writer_model": "claude-haiku-4-5-20251001",
    "writer_temperature": 0,
    "writer_input_tokens": 564,
    "writer_output_tokens": 111,
    "endpoint": "http://localhost:7200/repositories/hetionet",
    "sparql_generated": "PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?gene ?geneLabel
WHERE {
  ?anatomy rdfs:label \"ankle joint\" .
  ?anatomy hetio:expresses ?gene .
  ?gene a hetio:Gene .
  ?gene rdfs:label ?geneLabel .
}",
    "writer_reply_raw": "```sparql
PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?gene ?geneLabel
WHERE {
  ?anatomy rdfs:label \"ankle joint\" .
  ?anatomy hetio:expresses ?gene .
  ?gene a hetio:Gene .
  ?gene rdfs:label ?geneLabel .
}
```",
    "sparql": "PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?gene ?geneLabel
WHERE {
  ?anatomy rdfs:label \"ankle joint\" .
  ?anatomy hetio:expresses ?gene .
  ?gene a hetio:Gene .
  ?gene rdfs:label ?geneLabel .
}
LIMIT 200",
    "sparql_valid": true,
    "num_rows": 2,
    "context_tokenizer": "wordpunct-v1"
  },
  "judged": true,
  "passed": false,
  "score": 0,
  "verdict": "prose answer: recall 0/2 (precision not measurable)",
  "judge_details": {
    "expected_count": 2,
    "found_count": 0,
    "missing": [
      "CFL1",
      "SMU1"
    ],
    "precision": null,
    "recall": 0,
    "basis": "recall_only"
  }
}
```

the retriever did produce the right answer, the generator couldnt predict

is it that the: 
* the generator system prompt  needs to state that it should trust the retrieved context?
* the writer  system prompt needs to include context columns for sparql results. But, on negated intersections this might be not possible

# system prompt sha
is this only the prompt of the generator?

# wordpunt 
Why context_tokenizer is only set in some runs, couldnt find the pattern on a specific mechanism 

# judge deterministic and semantic
why run 
20260608T215424-closed_book-anthropic 
is both "judge": "deterministic-v1+semantic-v1",
i guess 10_fuzzy_semantic uses a semantic judge. cant that be recorded at the answer level?

# md's where  contract should say 

"retriever","mechanism"
"graph_neighborhood_1hop","neighborhood"
"closed_book","none"
"vector","dense"
"graph_sparqlgen","sparqlgen"
"graph_neighborhood_2hop","neighborhood"

# tracker of llm prompts
* should retriever have a system prompt sha?
* should semantic judge have a system prompt sha

# build refactor: non-obvious run params hidden behind os.environ.get()
The three MODEL knobs are now explicit CLI flags (--generator_model_family /
--writer_model_family / --judge_model_family, each no-default → fail-on-blank). The rest of a
run's tunable knobs are still read implicitly from env vars scattered across modules, so
configuring a run means knowing which module reads which variable. They should become explicit,
discoverable params (one RunConfig the harness threads down), keeping env only as a fallback —
the same treatment the model knobs just got. None of this changes provenance: every knob is
already logged in the manifest; this changes where a knob is *set*, not where it's *recorded*.

Remaining env-only knobs:
* GENERATOR_TEMPERATURE        — eval/run_eval.py (sampling temp of the model under test)
* SPARQLGEN_TEMPERATURE        — retrievers/sparqlgen.py (writer sampling temp)
* GRAPHDB_ENDPOINT             — retrievers/graph.py + retrievers/sparqlgen.py (the SPARQL endpoint)
* CHROMA_STORE                 — retrievers/vector.py (the vector store path)
* CORPUS_BUILD_ID              — eval/run_eval.py (overrides ingest/corpus/ACTIVE)

The two temperatures are the clearest next step — they belong beside their model flag
(--generator_temperature / --writer_temperature) so a temperature-as-factor run is set on the
command line, not via an env var the reader has to know exists. See the TODO(knobs) note in
eval/run_eval.py.

