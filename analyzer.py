import re
import spacy
import logging

class AcademicAnalyzer:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except:
            self.logger.warning("Spacy model 'en_core_web_sm' not found. NLP features will be limited.")
            self.nlp = None

    def analyze(self, text):
        """
        Analyzes the full text to extract structured information.
        """
        if not text:
            return {}

        data = {
            "background": self._extract_section(text, ["background", "introduction", "literature review", "引言", "研究背景", "文献综述"]),
            "significance": self._extract_section(text, ["significance", "contribution", "研究意义", "边际贡献"]),
            "methodology": self._extract_section(text, ["methodology", "research design", "empirical strategy", "model", "研究设计", "实证", "模型", "计量"]),
            "conclusions": self._extract_section(text, ["conclusion", "result", "finding", "结论", "发现"]),
            "variables": self._extract_variables(text)
        }
        
        # Summarize if too long (mock summary via truncation for this demo)
        if not data["background"] and len(text) > 500:
            # Fallback: take the first 1000 chars as background if not found
            data["background"] = text[:1000] + "..."
            
        data["background"] = data["background"][:1000] + "..." if len(data["background"]) > 1000 else data["background"]
        
        return data

    def _extract_section(self, text, keywords):
        """
        Basic section extraction based on keywords.
        """
        # Create a regex pattern to find headers
        # Allow loose matching for headers (e.g., "1. Introduction", "一、引言", "1 引言")
        # But ensure it's a short line (likely a header)
        pattern = r"(?i)^.{0,10}(" + "|".join(keywords) + r").{0,20}$"
        
        lines = text.split('\n')
        section_content = []
        in_section = False
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Check if line is a header
            if re.match(pattern, line):
                in_section = True
                continue
            
            # Stop if we hit another likely header
            if in_section:
                # Common next section headers or ending markers
                stop_pattern = r"(?i)^.{0,10}(References|Bibliography|Appendix|Data|Conclusion|Results|参考文献|附录|数据|结论|结果|模型|变量).{0,20}$"
                if re.match(stop_pattern, line) and line not in section_content: # Avoid self-triggering if keywords overlap
                    break
                section_content.append(line)
        
        return "\n".join(section_content).strip()

    def _extract_variables(self, text):
        """
        Heuristic extraction of variables.
        """
        variables = {
            "dependent": [],
            "independent": [],
            "mechanism": [],
            "controls": []
        }
        
        # Helper to extract context around a keyword
        def extract_context(keyword_pattern, text, limit=100):
            matches = []
            for m in re.finditer(keyword_pattern, text, re.IGNORECASE):
                start = m.end()
                # Extract next N chars, stop at newline
                content = text[start:start+limit].split('\n')[0]
                # Clean up punctuation
                content = re.sub(r'^[：:is\s]+', '', content)
                matches.append(content.strip())
            return matches

        # Dependent
        variables["dependent"] = extract_context(r"(?:dependent variable|被解释变量|outcome variable)", text)
        
        # Independent
        variables["independent"] = extract_context(r"(?:independent variable|core explanatory variable|解释变量|核心变量|key variable)", text)

        # Controls
        controls_raw = extract_context(r"(?:control variable[s]?|控制变量)", text)
        if controls_raw:
            # Try to split the first match
            first_match = controls_raw[0]
            controls = re.split(r'[,，、and和]', first_match)
            variables["controls"] = [c.strip() for c in controls if 1 < len(c.strip()) < 20] # Filter reasonable length

        return variables
