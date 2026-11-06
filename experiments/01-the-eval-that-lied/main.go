// agent-eval-go: a ~200-line doc-QA agent plus the eval that measures it.
//
// The agent answers questions about a fictional product by searching a local docs corpus
// (tools: search_docs, read_doc). The eval runs every question N times per configuration and
// records pass rate, steps, tokens, latency and cost. Nothing here is mocked: every run is a
// real call to the Claude API.
//
//	go run . -config A -runs 3 -out results/A.jsonl
//	go run . -summary results/A.jsonl results/B.jsonl results/C.jsonl
package main

import (
	"bufio"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/anthropics/anthropic-sdk-go/v2"
)

// ---------- configurations under test ----------

type Config struct {
	Name   string
	Model  string
	System string
	InUSD  float64 // $ per 1M input tokens
	OutUSD float64 // $ per 1M output tokens
}

const basePrompt = `You are the support assistant for Relayline, a webhook relay service.
Answer questions using ONLY the product documentation available through your tools.
Always search the docs before answering. If the docs do not contain the answer, say so.
Include the exact figure, header name or status code from the docs in your answer.`

var configs = map[string]Config{
	// A: baseline. B: "harmless" model swap to cut cost. C: "harmless" prompt tweak.
	"A": {"A-sonnet-base", "claude-sonnet-5-5", basePrompt, 2.00, 10.00},
	"B": {"B-haiku-base", "claude-haiku-5-5", basePrompt, 0.10, 0.50},
	"C": {"C-sonnet-concise", "claude-sonnet-5-5", basePrompt + "\nBe concise. Answer in one short sentence.", 2.00, 10.00},
}

// ---------- tools ----------

var tools = []anthropic.ToolUnionParam{
	{OfTool: &anthropic.ToolParam{
		Name:        "search_docs",
		Description: anthropic.String("Full-text search over the product docs. Returns matching lines with their file names."),
		InputSchema: anthropic.ToolInputSchemaParam{Properties: map[string]any{
			"query": map[string]any{"type": "string", "description": "words to look for"},
		}, Required: []string{"query"}},
	}},
	{OfTool: &anthropic.ToolParam{
		Name:        "read_doc",
		Description: anthropic.String("Read one documentation file in full by its file name."),
		InputSchema: anthropic.ToolInputSchemaParam{Properties: map[string]any{
			"name": map[string]any{"type": "string", "description": "file name, e.g. 02-pricing.md"},
		}, Required: []string{"name"}},
	}},
}

type corpus map[string]string // file name -> content

func loadCorpus(dir string) corpus {
	c := corpus{}
	entries, err := filepath.Glob(filepath.Join(dir, "*.md"))
	must(err)
	for _, p := range entries {
		b, err := os.ReadFile(p)
		must(err)
		c[filepath.Base(p)] = string(b)
	}
	return c
}

func (c corpus) search(query string) string {
	words := strings.Fields(strings.ToLower(query))
	type hit struct {
		file, line string
		score      int
	}
	var hits []hit
	for name, body := range c {
		for _, ln := range strings.Split(body, "\n") {
			low := strings.ToLower(ln)
			score := 0
			for _, w := range words {
				if strings.Contains(low, w) {
					score++
				}
			}
			if score > 0 {
				hits = append(hits, hit{name, strings.TrimSpace(ln), score})
			}
		}
	}
	sort.SliceStable(hits, func(i, j int) bool { return hits[i].score > hits[j].score })
	if len(hits) > 12 {
		hits = hits[:12]
	}
	if len(hits) == 0 {
		return "no matches"
	}
	var sb strings.Builder
	for _, h := range hits {
		fmt.Fprintf(&sb, "%s: %s\n", h.file, h.line)
	}
	return sb.String()
}

// ---------- the agent loop ----------

type Result struct {
	Config    string  `json:"config"`
	Model     string  `json:"model"`
	Run       int     `json:"run"`
	QID       string  `json:"qid"`
	Question  string  `json:"question"`
	Expected  string  `json:"expected"`
	Answer    string  `json:"answer"`
	Passed    bool    `json:"passed"`
	Steps     int     `json:"steps"`
	InTokens  int64   `json:"in_tokens"`
	OutTokens int64   `json:"out_tokens"`
	LatencyMS int64   `json:"latency_ms"`
	CostUSD   float64 `json:"cost_usd"`
	HTTPError string  `json:"http_error,omitempty"`
}

const maxSteps = 8

// trace, when non-nil, is called for every tool call and for the final answer (-ask mode only).
type traceFn func(kind, name, detail string)

func runAgent(ctx context.Context, client anthropic.Client, cfg Config, c corpus, question string, trace traceFn) Result {
	r := Result{Config: cfg.Name, Model: cfg.Model}
	start := time.Now()
	messages := []anthropic.MessageParam{anthropic.NewUserMessage(anthropic.NewTextBlock(question))}
	var answer strings.Builder
	for step := 0; step < maxSteps; step++ {
		resp, err := client.Messages.New(ctx, anthropic.MessageNewParams{
			Model:     cfg.Model,
			MaxTokens: 2000,
			System:    []anthropic.TextBlockParam{{Text: cfg.System}},
			Messages:  messages,
			Tools:     tools,
		})
		if err != nil {
			r.HTTPError = err.Error()
			break
		}
		r.Steps++
		r.InTokens += resp.Usage.InputTokens + resp.Usage.CacheReadInputTokens + resp.Usage.CacheCreationInputTokens
		r.OutTokens += resp.Usage.OutputTokens
		messages = append(messages, resp.ToParam())
		var toolResults []anthropic.ContentBlockParamUnion
		for _, block := range resp.Content {
			switch v := block.AsAny().(type) {
			case anthropic.TextBlock:
				answer.WriteString(v.Text)
			case anthropic.ToolUseBlock:
				var in map[string]string
				_ = json.Unmarshal([]byte(v.JSON.Input.Raw()), &in)
				var out string
				switch v.Name {
				case "search_docs":
					out = c.search(in["query"])
				case "read_doc":
					if body, ok := c[in["name"]]; ok {
						out = body
					} else {
						out = "no such file"
					}
				}
				if trace != nil {
					trace("tool", v.Name, fmt.Sprintf("%s -> %d chars, %d lines", v.JSON.Input.Raw(), len(out), strings.Count(out, "\n")+1))
				}
				toolResults = append(toolResults, anthropic.NewToolResultBlock(v.ID, out, false))
			}
		}
		if resp.StopReason != anthropic.StopReasonToolUse {
			break
		}
		messages = append(messages, anthropic.NewUserMessage(toolResults...))
	}
	r.Answer = strings.TrimSpace(answer.String())
	r.LatencyMS = time.Since(start).Milliseconds()
	r.CostUSD = float64(r.InTokens)/1e6*cfg.InUSD + float64(r.OutTokens)/1e6*cfg.OutUSD
	if trace != nil {
		trace("answer", "", r.Answer)
		trace("stats", "", fmt.Sprintf("steps=%d  in=%d out=%d tokens  %.1fs  $%.4f", r.Steps, r.InTokens, r.OutTokens, float64(r.LatencyMS)/1000, r.CostUSD))
	}
	return r
}

// ---------- grading ----------

func passes(answer, expected string) bool {
	a := strings.ToLower(answer)
	for _, alt := range strings.Split(expected, "|") {
		if strings.Contains(a, strings.ToLower(alt)) {
			return true
		}
	}
	return false
}

// ---------- eval runner ----------

type Question struct {
	ID       string `json:"id"`
	Question string `json:"question"`
	Expected string `json:"expected_contains"`
}

func loadQuestions(path string) []Question {
	f, err := os.Open(path)
	must(err)
	defer f.Close()
	var qs []Question
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		var q Question
		must(json.Unmarshal(sc.Bytes(), &q))
		qs = append(qs, q)
	}
	return qs
}

func runEval(cfgKey string, runs, workers int, out, questionsPath string) {
	cfg, ok := configs[cfgKey]
	if !ok {
		fatalf("unknown config %q (A, B or C)", cfgKey)
	}
	c := loadCorpus("corpus")
	qs := loadQuestions(questionsPath)
	must(os.MkdirAll(filepath.Dir(out), 0o755))
	f, err := os.Create(out)
	must(err)
	defer f.Close()
	client := anthropic.NewClient() // ANTHROPIC_API_KEY from the environment (see run.sh)
	fmt.Printf("%s%s%s  model=%s  %d questions x %d runs  workers=%d  grader=%s\n", bold, cfg.Name, reset, cfg.Model, len(qs), runs, workers, filepath.Base(questionsPath))
	t0 := time.Now()
	var passed, errs int
	var cost float64
	lat := make([]int64, 0, len(qs)*runs)

	type job struct {
		q   Question
		run int
	}
	jobs := make(chan job)
	var mu sync.Mutex
	var wg sync.WaitGroup
	done, total := 0, len(qs)*runs
	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := range jobs {
				r := runAgent(context.Background(), client, cfg, c, j.q.Question, nil)
				r.Run, r.QID, r.Question, r.Expected = j.run, j.q.ID, j.q.Question, j.q.Expected
				r.Passed = r.HTTPError == "" && passes(r.Answer, j.q.Expected)
				line, _ := json.Marshal(r)
				mu.Lock()
				f.Write(append(line, '\n'))
				done++
				mark := green + "PASS" + reset
				if !r.Passed {
					mark = red + "FAIL" + reset
				} else {
					passed++
				}
				if r.HTTPError != "" {
					errs++
				}
				cost += r.CostUSD
				lat = append(lat, r.LatencyMS)
				fmt.Printf("%s[%3d/%d]%s run%d %s  %s  steps=%d  %4.1fs  $%.4f  %s%s%s\n", dim, done, total, reset, j.run, j.q.ID, mark, r.Steps, float64(r.LatencyMS)/1000, r.CostUSD, dim, clip(j.q.Question, 48), reset)
				mu.Unlock()
			}
		}()
	}
	for run := 1; run <= runs; run++ {
		for _, q := range qs {
			jobs <- job{q, run}
		}
	}
	close(jobs)
	wg.Wait()
	sort.Slice(lat, func(i, j int) bool { return lat[i] < lat[j] })
	rate := 100 * float64(passed) / float64(total)
	fmt.Printf("%sdone%s  %d runs  pass %d/%d = %s%.1f%%%s  errors %d  p50 %.1fs  $%.2f total  %s  -> %s\n",
		bold, reset, total, passed, total, bold, rate, reset, errs, float64(lat[len(lat)/2])/1000, cost, time.Since(t0).Round(time.Second), out)
}

const (
	bold  = "\033[1m"
	dim   = "\033[2m"
	green = "\033[32m"
	red   = "\033[1;31m"
	reset = "\033[0m"
)

func clip(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n-1] + "…"
}

// ---------- ask: one question, with the tool calls shown ----------

func ask(cfgKey, question string) {
	cfg, ok := configs[cfgKey]
	if !ok {
		fatalf("unknown config %q (A, B or C)", cfgKey)
	}
	c := loadCorpus("corpus")
	client := anthropic.NewClient()
	fmt.Printf("%s%s%s  %s\n%sQ:%s %s\n", bold, cfg.Name, reset, cfg.Model, bold, reset, question)
	step := 0
	runAgent(context.Background(), client, cfg, c, question, func(kind, name, detail string) {
		switch kind {
		case "tool":
			step++
			fmt.Printf("  %s%d. tool%s %s%s%s  %s%s%s\n", dim, step, reset, green, name, reset, dim, detail, reset)
		case "answer":
			fmt.Printf("%sA:%s %s\n", bold, reset, detail)
		case "stats":
			fmt.Printf("%s%s%s\n", dim, detail, reset)
		}
	})
}

// ---------- regrade: re-score saved answers with another grader, no API calls ----------

func regrade(in, questionsPath, out string) {
	exp := map[string]string{}
	for _, q := range loadQuestions(questionsPath) {
		exp[q.ID] = q.Expected
	}
	f, err := os.Open(in)
	must(err)
	defer f.Close()
	must(os.MkdirAll(filepath.Dir(out), 0o755))
	o, err := os.Create(out)
	must(err)
	defer o.Close()
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	n, before, after := 0, 0, 0
	for sc.Scan() {
		var r Result
		must(json.Unmarshal(sc.Bytes(), &r))
		n++
		if r.Passed {
			before++
		}
		e, ok := exp[r.QID]
		if !ok || strings.TrimSpace(e) == "" {
			fatalf("regrade: no expectation for %s in %s (an empty expectation would pass every answer)", r.QID, questionsPath)
		}
		r.Expected = e
		r.Passed = r.HTTPError == "" && passes(r.Answer, r.Expected)
		if r.Passed {
			after++
		}
		line, _ := json.Marshal(r)
		o.Write(append(line, '\n'))
	}
	fmt.Printf("%s%s%s: re-scored %d saved answers with %s, 0 API calls: pass %d -> %d (%.1f%% -> %.1f%%) -> %s\n",
		bold, filepath.Base(in), reset, n, filepath.Base(questionsPath), before, after, 100*float64(before)/float64(n), 100*float64(after)/float64(n), out)
}

// ---------- summary ----------

func summarize(paths []string) {
	fmt.Println("| config | model | runs | pass rate | errors | p50 latency | avg steps | in tok/run | out tok/run | $ per 100 answers |")
	fmt.Println("|---|---|---|---|---|---|---|---|---|---|")
	for _, p := range paths {
		f, err := os.Open(p)
		must(err)
		var rs []Result
		sc := bufio.NewScanner(f)
		sc.Buffer(make([]byte, 1<<20), 1<<20)
		for sc.Scan() {
			var r Result
			must(json.Unmarshal(sc.Bytes(), &r))
			rs = append(rs, r)
		}
		f.Close()
		if len(rs) == 0 {
			continue
		}
		var passed, errs, steps int
		var in, out int64
		var cost float64
		lat := make([]int64, 0, len(rs))
		for _, r := range rs {
			if r.Passed {
				passed++
			}
			if r.HTTPError != "" {
				errs++
			}
			steps += r.Steps
			in += r.InTokens
			out += r.OutTokens
			cost += r.CostUSD
			lat = append(lat, r.LatencyMS)
		}
		sort.Slice(lat, func(i, j int) bool { return lat[i] < lat[j] })
		n := float64(len(rs))
		fmt.Printf("| %s | %s | %d | %.1f%% | %d | %.1f s | %.2f | %.0f | %.0f | $%.3f |\n",
			rs[0].Config, rs[0].Model, len(rs), 100*float64(passed)/n, errs,
			float64(lat[len(lat)/2])/1000, float64(steps)/n, float64(in)/n, float64(out)/n, cost/n*100)
	}
}

// ---------- main ----------

func main() {
	cfg := flag.String("config", "", "configuration to run: A, B or C")
	runs := flag.Int("runs", 3, "runs per question")
	workers := flag.Int("workers", 4, "parallel agents")
	out := flag.String("out", "", "output JSONL (default results/<config>.jsonl)")
	questions := flag.String("questions", "questions.jsonl", "eval set (questions.v1.jsonl = original grader)")
	summary := flag.Bool("summary", false, "print a markdown summary of the JSONL files given as args")
	askQ := flag.String("ask", "", "answer one question with -config, showing the tool calls")
	regradeIn := flag.String("regrade", "", "re-score this JSONL with the grader in -questions, writing -out (no API calls)")
	flag.Parse()
	if *summary {
		summarize(flag.Args())
		return
	}
	if *askQ != "" {
		if *cfg == "" {
			*cfg = "A"
		}
		ask(*cfg, *askQ)
		return
	}
	if *regradeIn != "" {
		if *out == "" {
			fatalf("-regrade needs -out")
		}
		regrade(*regradeIn, *questions, *out)
		return
	}
	if *cfg == "" {
		fatalf("usage: -config A|B|C [-runs N] [-out file]   or   -summary files...")
	}
	if *out == "" {
		*out = filepath.Join("results", *cfg+".jsonl")
	}
	runEval(*cfg, *runs, *workers, *out, *questions)
}

func must(err error) {
	if err != nil {
		fatalf("%v", err)
	}
}

func fatalf(format string, a ...any) {
	fmt.Fprintf(os.Stderr, format+"\n", a...)
	os.Exit(1)
}
