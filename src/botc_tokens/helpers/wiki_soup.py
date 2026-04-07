"""A class to act as a cache for wiki access. That way we don't have to keep hitting the wiki for the same page."""
import json
import urllib.error
from urllib.request import urlopen

from bs4 import BeautifulSoup

from .. import data_dir


class WikiSoup:
    """A class to act as a cache for wiki access."""

    def __init__(self, script_filter: str = "Experimental"):
        """Prep the reminders and wiki soup."""
        self.wiki_soups = {}
        self.reminders = {}
        with open(data_dir / "known_reminders.json", "r") as f:
            self.reminders = json.load(f)
        self.reminder_overrides = {}
        self.role_data = {}
        self.night_data = {"firstNight": [], "otherNight": []}
        self._script_filter = script_filter
    
    def load_from_web(self):
        import subprocess
        import json
        import tempfile
        import requests
    
        url = "https://script.bloodontheclocktower.com/workspace.3c82003c.js"
        js = requests.get(url).text
    
        # Create a temporary Node script
        node_script = f"""
        const vm = require('vm');
    
        let sandbox = {{
            console,
            window: {{}},
            self: {{}},
            global: {{}}
        }};
    
        vm.createContext(sandbox);
    
        try {{
            vm.runInContext(`{js.replace('`', '\\`')}`, sandbox);
    
            let out = {{
                roles: typeof sandbox.roles !== 'undefined' ? sandbox.roles : null,
                night: typeof sandbox.nightSheet !== 'undefined' ? sandbox.nightSheet : null
            }};
    
            console.log(JSON.stringify(out));
        }} catch (e) {{
            console.log(JSON.stringify({{error: e.toString()}}));
        }}
        """
    
        with tempfile.NamedTemporaryFile(delete=False, suffix=".js") as f:
            f.write(node_script.encode("utf-8"))
            path = f.name
    
        result = subprocess.check_output(["node", path]).decode("utf-8")
        data = json.loads(result)
    
        if data.get("roles"):
            self.role_data = data["roles"]
    
        if data.get("night"):
            self.night_data = data["night"]
    
        if data.get("error"):
            raise RuntimeError(data["error"])
    
    def _get_wiki_soup(self, role_name):
        """Take a role name and return a BeautifulSoup object for the role's wiki page."""
        # Check if we have already seen this role
        role_name = role_name.replace(" ", "_")
        if role_name not in self.wiki_soups:
            # Make a special check for Spirit of Ivory, since it has a different capitalization scheme.
            url = f"https://wiki.bloodontheclocktower.com/{role_name}"
            try:
                html = urlopen(url).read()
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    raise RuntimeError(f"Could not find role {role_name} at {url}")
                else:
                    raise
            self.wiki_soups[role_name] = BeautifulSoup(html, 'html5lib')
        return self.wiki_soups[role_name]

    def get_ability_text(self, role_name):
        """Take a role name and grab the ability description."""
        soup = self._get_wiki_soup(role_name)
        summary_title = soup.find(id="Summary")
        if not summary_title:
            raise RuntimeError(f"Could not find summary section for {role_name}")
        tag = summary_title.parent.find_next_sibling("p")
        if not tag:
            raise RuntimeError(f"Could not find ability description for {role_name}")
        ability = tag.get_text()
        ability = ability.replace("\n", " ")
        ability = ability.strip('" ')
        ability = ability.replace("\"", "'")
        return ability

    def get_reminders(self, role_name):
        """Take a role name and grab the reminders."""
        # First check if we have the role in the override reminders file
        if role_name in self.reminder_overrides:
            return self.reminder_overrides[role_name]

        # Next check if we have the role in the local reminders file
        if role_name in self.reminders:
            return self.reminders[role_name]

        # If we don't have the role, go get it from the wiki
        reminders = set()
        soup = self._get_wiki_soup(role_name)
        reminder_title = soup.find(id="How_to_Run")
        if not reminder_title:
            raise RuntimeError(f"Could not find 'How To Run' section for {role_name}")
        paragraphs = reminder_title.parent.find_next_siblings("p")
        for paragraph in paragraphs:
            bold_list = paragraph.find_all("b")
            for bold in bold_list:
                text = bold.get_text()
                if text.isupper():
                    disallowed_reminders = [
                        "YOU ARE",
                        "THIS PLAYER IS",
                        "THIS CHARACTER SELECTED YOU",
                        "THESE CHARACTERS ARE NOT IN PLAY",
                        "THIS IS THE DEMON",
                        "THESE ARE YOUR MINIONS",
                    ]
                    if text not in disallowed_reminders:
                        reminders.add(text)
        return list(reminders)

    def get_big_icon_url(self, role_name):
        """Take a role name and grab the corresponding icon url from the wiki."""
        soup = self._get_wiki_soup(role_name)
        icon_tag = soup.select_one("#character-details img")
        if not icon_tag:
            raise RuntimeError(f"Could not find icon for {role_name}")
        icon_url = icon_tag["src"]
        return icon_url
