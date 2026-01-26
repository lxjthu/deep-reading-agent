import os
import pandas as pd
import argparse
import logging
import json
import concurrent.futures
from tqdm import tqdm
from openai import OpenAI
from dotenv import load_dotenv
import re

# Import the new parser factory
from parsers import get_parser

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class PromptManager:
    PROMPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts", "literature_filter")

    @classmethod
    def load_prompt(cls, mode_name):
        """Loads a prompt template from the prompts directory."""
        file_path = os.path.join(cls.PROMPT_DIR, f"{mode_name}.md")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Prompt file not found: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

    @staticmethod
    def format_prompt(template, paper_data, topic):
        """Formats the prompt with paper details and topic using replace to avoid brace issues."""
        p = template
        p = p.replace("{title}", str(paper_data.get('Title', '')))
        p = p.replace("{journal}", str(paper_data.get('Journal', '')))
        p = p.replace("{year}", str(paper_data.get('Year', '')))
        p = p.replace("{authors}", str(paper_data.get('Authors', '')))
        p = p.replace("{abstract}", str(paper_data.get('Abstract', '')))
        p = p.replace("{topic}", str(topic))
        return p

class AIEvaluator:
    def __init__(self, model="deepseek-chat"):
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.base_url = "https://api.deepseek.com"
        self.model = model
        
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY not found in environment variables.")

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def evaluate_paper(self, paper_row, prompt_template, topic):
        """Evaluates a single paper using LLM."""
        try:
            user_content = PromptManager.format_prompt(prompt_template, paper_row, topic)
            
            # DEBUG LOG
            # logger.info(f"--- Prompt Preview ---\n{user_content[:200]}...\n--------------------")
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful research assistant. Output strictly in JSON."},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            # DEBUG LOG
            # logger.info(f"--- Raw Response ---\n{content}\n--------------------")
            
            # Simple JSON repair if needed
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                # Fallback: try to find JSON block
                match = re.search(r'\{[\s\S]*\}', content)
                if match:
                    try:
                        return json.loads(match.group(0))
                    except:
                        pass
                return {"error": "JSON Parse Error", "raw_output": content}
                
        except Exception as e:
            return {"error": str(e)}

    def evaluate_batch(self, df, prompt_template, topic, max_workers=5):
        """Evaluates a batch of papers concurrently."""
        results = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Create a list of futures
            future_to_index = {
                executor.submit(self.evaluate_paper, row, prompt_template, topic): index 
                for index, row in df.iterrows()
            }
            
            # Use tqdm for progress bar
            for future in tqdm(concurrent.futures.as_completed(future_to_index), total=len(df), desc="AI Evaluating"):
                index = future_to_index[future]
                try:
                    res = future.result()
                    if "error" in res:
                        logger.error(f"Error in row {index}: {res['error']}")
                        if "raw_output" in res:
                            logger.error(f"Raw Output: {res['raw_output'][:500]}...") # Print first 500 chars
                    res['original_index'] = index # Keep track of original index
                    results.append(res)
                except Exception as e:
                    logger.error(f"Error processing row {index}: {e}")
                    results.append({"original_index": index, "error": str(e)})
        
        return results

def filter_literature(df, min_year=None, keywords=None):
    initial_count = len(df)
    if min_year:
        df['Year_Num'] = pd.to_numeric(df['Year'], errors='coerce')
        df = df[df['Year_Num'] >= min_year]
    if keywords:
        mask = pd.Series(False, index=df.index)
        for kw in keywords:
            mask |= df['Title'].str.contains(kw, case=False, na=False)
            mask |= df['Abstract'].str.contains(kw, case=False, na=False)
        df = df[mask]
    logger.info(f"Filtered: {initial_count} -> {len(df)} records")
    return df

def main():
    parser = argparse.ArgumentParser(description="Smart Literature Filter for Web of Science and CNKI exports")
    parser.add_argument("input_file", help="Path to the savedrecs.txt (WoS) or CNKI text file")
    parser.add_argument("--output", default="literature_summary.xlsx", help="Output Excel file path")
    parser.add_argument("--min_year", type=int, help="Filter papers published on or after this year")
    parser.add_argument("--keywords", nargs="+", help="Filter by keywords (in Title/Abstract)")
    
    # AI Arguments
    parser.add_argument("--ai_mode", choices=['explorer', 'reviewer', 'empiricist'], help="Enable AI evaluation mode")
    parser.add_argument("--topic", help="Research topic for AI evaluation (Required if ai_mode is set)")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of papers for AI eval (0 for all)")
    
    args = parser.parse_args()
    
    # 1. Parse using Factory
    parser_instance = get_parser(args.input_file)
    if not parser_instance:
        logger.error("Unsupported file format or file not found.")
        return

    parser_instance.parse()
    df = parser_instance.to_dataframe()
    
    if df.empty:
        logger.warning("No records found.")
        return

    # 2. Filter
    if args.min_year or args.keywords:
        df = filter_literature(df, args.min_year, args.keywords)

    if df.empty:
        logger.warning("No papers matched criteria.")
        return

    # 3. AI Evaluation
    if args.ai_mode:
        if not args.topic:
            logger.error("--topic is required when using --ai_mode")
            return
            
        logger.info(f"Starting AI Evaluation in '{args.ai_mode}' mode for topic: '{args.topic}'")
        
        # Limit processing if requested (save money/time)
        if args.limit > 0:
            logger.info(f"Limiting AI evaluation to top {args.limit} rows.")
            df_to_eval = df.head(args.limit).copy()
        else:
            df_to_eval = df.copy()

        try:
            evaluator = AIEvaluator()
            prompt_template = PromptManager.load_prompt(args.ai_mode)
            
            ai_results = evaluator.evaluate_batch(df_to_eval, prompt_template, args.topic)
            
            # Merge results
            # Convert list of dicts to DataFrame, indexed by 'original_index'
            ai_df = pd.DataFrame(ai_results)
            if not ai_df.empty:
                ai_df.set_index('original_index', inplace=True)
                
                # Join with original DF
                df = df.join(ai_df, how='left')
                
                # Sort by Score if available
                if 'score' in df.columns:
                    df['score'] = pd.to_numeric(df['score'], errors='coerce')
                    df = df.sort_values(by='score', ascending=False)
                    
        except Exception as e:
            logger.error(f"AI Evaluation failed: {e}")

    # 4. Export
    if 'Year_Num' in df.columns:
        df = df.drop(columns=['Year_Num'])
        
    df.to_excel(args.output, index=False)
    logger.info(f"Exported summary to {args.output}")
    print(f"Success! Processed {len(df)} papers. Check {args.output}")

if __name__ == "__main__":
    main()
