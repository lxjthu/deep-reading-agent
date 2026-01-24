import os
import re
import logging
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class StataRefiner:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # DeepSeek API Configuration
        # Users need to set DEEPSEEK_API_KEY in .env
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.base_url = "https://api.deepseek.com"
        # Use deepseek-reasoner for Thinking Mode (R1)
        self.model = "deepseek-reasoner"
        
        if not self.api_key:
            self.logger.warning("DEEPSEEK_API_KEY not found. Please add it to .env")
            self.client = None
        else:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def refine_code(self, methodology_summary, variable_info, filename=""):
        """
        Generates expert-level Stata code based on methodology and variables.
        """
        if not self.client:
            return "// Error: No API Key configured for Stata refinement."

        prompt = f"""
        You are Daron Acemoglu, a world-renowned Professor of Economics at MIT and a master of Applied Econometrics.
        You are also an expert in Stata programming, known for writing robust, production-grade replication code.

        Your task is to write DETAILED, EXECUTABLE Stata code for the following research paper context.
        
        Paper: {filename}
        
        # Methodology Context
        {methodology_summary}
        
        # Variable Definitions
        {variable_info}
        
        # Requirements
        1. **Code Quality**: Write complete, runnable Stata code (`.do` file format).
        2. **Robustness**: Include standard robustness checks (e.g., parallel trends for DID, overidentification tests for IV, placebo tests).
        3. **Comments**: Add detailed comments in **CHINESE (Simplified)** explaining WHY you are running each command and interpreting potential results.
        4. **Best Practices**: Use `reghdfe` for high-dimensional fixed effects, `estout/outreg2` for exporting, and cluster standard errors appropriately.
        5. **Notes**: Add a section at the end called "Empirical Notes" (实证研究注意事项), listing potential pitfalls (e.g., endogeneity concerns, measurement errors) specific to this study's design. Use **CHINESE** for this section.
        
        # Output Format
        Return ONLY the Stata code block and the Notes section. Do not include conversational filler.
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are Daron Acemoglu, an expert econometrics professor. You explain concepts in Chinese."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2 
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            self.logger.error(f"Stata Refinement failed: {e}")
            return f"// Error generating Stata code: {str(e)}"

    def update_markdown_report(self, md_path, refined_code):
        """
        Updates the existing markdown report with the refined Stata code.
        """
        if not os.path.exists(md_path):
            self.logger.warning(f"Report file not found: {md_path}")
            return

        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Replace the old Stata section (simple regex replacement)
        # Looking for "## 4. Stata 代码建议" and everything after it
        new_section = f"""## 4. Stata 代码建议 (Expert Refined)

{refined_code}
"""
        
        # Escape backslashes in the replacement string to avoid re.sub errors
        # This fixes "bad escape \Y" errors if Stata code contains paths or macros
        new_section_escaped = new_section.replace('\\', '\\\\')

        # Regex to find the section header and replace until end of file or next H1/H2 (though it's usually the last section)
        pattern = r"## 4\. Stata 代码建议[\s\S]*"
        
        if re.search(pattern, content):
            new_content = re.sub(pattern, new_section_escaped, content)
        else:
            # Append if not found
            new_content = content + "\n\n" + new_section

        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
