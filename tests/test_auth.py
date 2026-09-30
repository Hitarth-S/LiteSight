import pytest
from server import SERVER_EXECUTOR
from src.agents.swarm import SpeculativeActionAgent
from src.orchestrator.bus import LocalMessageBus
from src.browser.engine import BrowserEngine


def test_login_input_resolution_no_premature_auto_enter():
    """
    Ensures that input fields with placeholders like 'Enter your username' or 'Enter your password'
    do NOT trigger TYPE_AND_SUBMIT (which would prematurely fire the Enter key before the other field is filled).
    """
    elements = [
        {
            "index": 1,
            "tag": "input",
            "role": "textbox",
            "label": "Enter your username",
            "value": "",
            "is_visible": True,
            "bounding_box": {"x": 100, "y": 100, "width": 250, "height": 35}
        },
        {
            "index": 2,
            "tag": "input",
            "role": "textbox",
            "label": "Enter your password",
            "value": "",
            "is_visible": True,
            "bounding_box": {"x": 100, "y": 150, "width": 250, "height": 35}
        },
        {
            "index": 3,
            "tag": "button",
            "role": "button",
            "label": "Log In",
            "value": "",
            "is_visible": True,
            "bounding_box": {"x": 100, "y": 200, "width": 120, "height": 40}
        }
    ]

    # Typing username must be TYPE_TEXT, never TYPE_AND_SUBMIT
    action_user = SERVER_EXECUTOR._resolve_fast_path_action("type 'alice' into username", elements)
    assert action_user is not None
    assert action_user["operation"] == "TYPE_TEXT"
    assert action_user["target_index"] == 1
    assert action_user["text_value"] == "alice"

    # Typing password must be TYPE_TEXT, never TYPE_AND_SUBMIT
    action_pass = SERVER_EXECUTOR._resolve_fast_path_action("type 'secret123' into password", elements)
    assert action_pass is not None
    assert action_pass["operation"] == "TYPE_TEXT"
    assert action_pass["target_index"] == 2
    assert action_pass["text_value"] == "secret123"

    # Clicking Log In button
    action_submit = SERVER_EXECUTOR._resolve_fast_path_action("click log in", elements)
    assert action_submit is not None
    assert action_submit["operation"] == "CLICK"
    assert action_submit["target_index"] == 3


def test_login_explicit_submit():
    """When the user explicitly asks to submit, TYPE_AND_SUBMIT must be returned."""
    elements = [
        {
            "index": 1,
            "tag": "input",
            "role": "textbox",
            "label": "Password",
            "value": "",
            "is_visible": True,
            "bounding_box": {"x": 100, "y": 150, "width": 250, "height": 35}
        }
    ]
    action = SERVER_EXECUTOR._resolve_fast_path_action("type 'secret123' into password and submit", elements)
    assert action is not None
    assert action["operation"] == "TYPE_AND_SUBMIT"
    assert action["target_index"] == 1
    assert action["text_value"] == "secret123"


def test_signup_intent_resolution():
    """Verifies matching for sign up and register buttons vs login buttons."""
    elements = [
        {
            "index": 10,
            "tag": "a",
            "role": "link",
            "label": "Already have an account? Sign In",
            "value": "",
            "is_visible": True,
            "bounding_box": {"x": 100, "y": 300, "width": 200, "height": 30}
        },
        {
            "index": 11,
            "tag": "button",
            "role": "button",
            "label": "Create Account",
            "value": "",
            "is_visible": True,
            "bounding_box": {"x": 100, "y": 250, "width": 150, "height": 40}
        }
    ]

    action_signup = SERVER_EXECUTOR._resolve_fast_path_action("click create account", elements)
    assert action_signup is not None
    assert action_signup["operation"] == "CLICK"
    assert action_signup["target_index"] == 11


def test_swarm_auth_resolution_parity():
    """Verifies that SpeculativeActionAgent in edge swarm architecture maintains parity with executor."""
    bus = LocalMessageBus()
    agent = SpeculativeActionAgent(bus)

    elements = [
        {
            "index": 1,
            "tag": "input",
            "role": "textbox",
            "label": "Enter your username",
            "value": "",
            "is_visible": True,
            "bounding_box": {"x": 100, "y": 100, "width": 250, "height": 35}
        },
        {
            "index": 2,
            "tag": "input",
            "role": "textbox",
            "label": "Enter your password",
            "value": "",
            "is_visible": True,
            "bounding_box": {"x": 100, "y": 150, "width": 250, "height": 35}
        },
        {
            "index": 3,
            "tag": "button",
            "role": "button",
            "label": "Sign In",
            "value": "",
            "is_visible": True,
            "bounding_box": {"x": 100, "y": 200, "width": 100, "height": 40}
        }
    ]

    match_user = agent._match_element("type 'john_doe' into username", elements)
    assert match_user is not None
    assert match_user["operation"] == "TYPE_TEXT"
    assert match_user["target_index"] == 1
    assert match_user["text_value"] == "john_doe"

    match_pass = agent._match_element("type 'mypassword' into password", elements)
    assert match_pass is not None
    assert match_pass["operation"] == "TYPE_TEXT"
    assert match_pass["target_index"] == 2

    match_btn = agent._match_element("click sign in", elements)
    assert match_btn is not None
    assert match_btn["operation"] == "CLICK"
    assert match_btn["target_index"] == 3


def test_browser_engine_storage_state_interface():
    """Verifies BrowserEngine constructor and persistence attributes."""
    engine = BrowserEngine(headless=True, storage_state_path="auth_session.json")
    assert engine.storage_state_path == "auth_session.json"
    assert engine.headless is True


def test_flask_sample_page_element_detection_and_select():
    """
    Verifies that a sample page (e.g. written via Flask) containing:
    - Username input with associated label
    - Password input with associated label
    - Role select dropdown with associated label and options (Admin, User, Guest)
    - Login submit button
    is cleanly resolved by SERVER_EXECUTOR fast-path without misidentifying dropdowns as clicks
    or confusing username/password fields.
    """
    flask_elements = [
        {
            "index": 1,
            "tag": "input",
            "role": "textbox",
            "label": "Username username",
            "value": "",
            "is_visible": True,
            "bounding_box": {"x": 50, "y": 80, "width": 200, "height": 30}
        },
        {
            "index": 2,
            "tag": "input",
            "role": "textbox",
            "label": "Password password",
            "value": "",
            "is_visible": True,
            "bounding_box": {"x": 50, "y": 130, "width": 200, "height": 30}
        },
        {
            "index": 3,
            "tag": "select",
            "role": "combobox",
            "label": "Role role Admin User Guest",
            "value": "Admin",
            "is_visible": True,
            "bounding_box": {"x": 50, "y": 180, "width": 150, "height": 30}
        },
        {
            "index": 4,
            "tag": "button",
            "role": "button",
            "label": "Login",
            "value": "",
            "is_visible": True,
            "bounding_box": {"x": 50, "y": 230, "width": 100, "height": 35}
        }
    ]

    # 1. Fill username
    act_user = SERVER_EXECUTOR._resolve_fast_path_action("type 'john_doe' into username", flask_elements)
    assert act_user is not None
    assert act_user["operation"] == "TYPE_TEXT"
    assert act_user["target_index"] == 1
    assert act_user["text_value"] == "john_doe"

    # 2. Fill password
    act_pass = SERVER_EXECUTOR._resolve_fast_path_action("type 'SecretPass123' into password", flask_elements)
    assert act_pass is not None
    assert act_pass["operation"] == "TYPE_TEXT"
    assert act_pass["target_index"] == 2
    assert act_pass["text_value"] == "SecretPass123"

    # 3. Select 'Admin' from role dropdown
    act_select_admin = SERVER_EXECUTOR._resolve_fast_path_action("select 'Admin' from role dropdown", flask_elements)
    assert act_select_admin is not None
    assert act_select_admin["operation"] == "SELECT"
    assert act_select_admin["target_index"] == 3
    assert act_select_admin["text_value"] == "Admin"

    # 4. Choose 'User' in role (different wording without quotes)
    act_choose_user = SERVER_EXECUTOR._resolve_fast_path_action("choose 'User' in role", flask_elements)
    assert act_choose_user is not None
    assert act_choose_user["operation"] == "SELECT"
    assert act_choose_user["target_index"] == 3
    assert act_choose_user["text_value"] == "User"

    # 5. Click Login button
    act_login = SERVER_EXECUTOR._resolve_fast_path_action("click login", flask_elements)
    assert act_login is not None
    assert act_login["operation"] == "CLICK"
    assert act_login["target_index"] == 4


def test_flask_select_swarm_parity():
    """Verifies that SpeculativeActionAgent matches dropdown selection for Flask forms."""
    bus = LocalMessageBus()
    agent = SpeculativeActionAgent(bus)

    flask_elements = [
        {
            "index": 1,
            "tag": "input",
            "role": "textbox",
            "label": "Username username",
            "value": "",
            "is_visible": True,
            "bounding_box": {"x": 50, "y": 80, "width": 200, "height": 30}
        },
        {
            "index": 2,
            "tag": "select",
            "role": "combobox",
            "label": "Role role Admin User Guest",
            "value": "Admin",
            "is_visible": True,
            "bounding_box": {"x": 50, "y": 180, "width": 150, "height": 30}
        }
    ]

    action = agent._match_element("select 'Admin' from role dropdown", flask_elements)
    assert action is not None
    assert action["operation"] == "SELECT"
    assert action["target_index"] == 2
    assert action["text_value"] == "Admin"


def test_arrow_and_mapping_syntax_resolution():
    """
    Verifies that key-value mappings like 'username -> admin', 'password -> admin',
    and 'select role as -> admin' correctly resolve to typing and dropdown selection
    instead of falling back to arbitrary clicks.
    """
    elements = [
        {
            "index": 5,
            "tag": "input",
            "role": "textbox",
            "label": "Username Only letters, numbers, and underscores are allowed username username",
            "value": "",
            "is_visible": True,
            "bounding_box": {"x": 640, "y": 241, "width": 300, "height": 38}
        },
        {
            "index": 6,
            "tag": "input",
            "role": "textbox",
            "label": "Password password password",
            "value": "",
            "is_visible": True,
            "bounding_box": {"x": 640, "y": 326, "width": 300, "height": 38}
        },
        {
            "index": 7,
            "tag": "select",
            "role": "combobox",
            "label": "Role role role Select your role Patient Donor Hospital Operative Admin",
            "value": "",
            "is_visible": True,
            "bounding_box": {"x": 640, "y": 410, "width": 300, "height": 38}
        },
        {
            "index": 8,
            "tag": "button",
            "role": "button",
            "label": "Login",
            "value": "",
            "is_visible": True,
            "bounding_box": {"x": 640, "y": 480, "width": 300, "height": 42}
        }
    ]

    # 1. Preamble step on active login form should NOT prematurely click submit
    intro_act = SERVER_EXECUTOR._resolve_fast_path_action("login using the credentials", elements)
    assert intro_act is not None
    assert intro_act["operation"] == "WAIT"

    # 2. 'username -> admin' MUST be TYPE_TEXT with text_value 'admin' on index 5
    act_user = SERVER_EXECUTOR._resolve_fast_path_action("username -> admin", elements)
    assert act_user is not None
    assert act_user["operation"] == "TYPE_TEXT"
    assert act_user["target_index"] == 5
    assert act_user["text_value"] == "admin"

    # 3. 'password -> admin' MUST be TYPE_TEXT with text_value 'admin' on index 6
    act_pass = SERVER_EXECUTOR._resolve_fast_path_action("password -> admin", elements)
    assert act_pass is not None
    assert act_pass["operation"] == "TYPE_TEXT"
    assert act_pass["target_index"] == 6
    assert act_pass["text_value"] == "admin"

    # 4. 'select role as -> admin' MUST be SELECT with text_value 'admin' on index 7 (not 'role')
    act_role = SERVER_EXECUTOR._resolve_fast_path_action("select role as -> admin", elements)
    assert act_role is not None
    assert act_role["operation"] == "SELECT"
    assert act_role["target_index"] == 7
    assert act_role["text_value"].lower() == "admin"

    # 5. 'click login' clicks the login submit button
    act_submit = SERVER_EXECUTOR._resolve_fast_path_action("click login", elements)
    assert act_submit is not None
    assert act_submit["operation"] == "CLICK"
    assert act_submit["target_index"] == 8


def test_planner_fallback_auto_submit_generation():
    """
    Verifies that the planner fallback decomposes multi-field auth goals
    and appends a final submit/click login step when one is not explicitly written.
    """
    from src.orchestrator.executor import HighLevelPlanner
    planner = HighLevelPlanner()
    goal = "login using the credentials, username -> admin , password -> admin , select role as -> admin "
    plan = planner._fallback_decompose_goal(goal)
    assert len(plan) == 5
    assert plan[0] == "login using the credentials"
    assert plan[1] == "username -> admin"
    assert plan[2] == "password -> admin"
    assert plan[3] == "select role as -> admin"
    assert plan[4] == "click login"


def test_swarm_arrow_syntax_parity():
    """Verifies that SpeculativeActionAgent correctly resolves arrow mapping syntax."""
    bus = LocalMessageBus()
    agent = SpeculativeActionAgent(bus)

    elements = [
        {
            "index": 5,
            "tag": "input",
            "role": "textbox",
            "label": "Username username",
            "value": "",
            "is_visible": True,
            "bounding_box": {"x": 100, "y": 100, "width": 200, "height": 30}
        },
        {
            "index": 7,
            "tag": "select",
            "role": "combobox",
            "label": "Role role Select your role Patient Donor Hospital Operative Admin",
            "value": "",
            "is_visible": True,
            "bounding_box": {"x": 100, "y": 200, "width": 200, "height": 30}
        }
    ]

    user_act = agent._match_element("username -> admin", elements)
    assert user_act is not None
    assert user_act["operation"] == "TYPE_TEXT"
    assert user_act["target_index"] == 5
    assert user_act["text_value"] == "admin"

    role_act = agent._match_element("select role as -> admin", elements)
    assert role_act is not None
    assert role_act["operation"] == "SELECT"
    assert role_act["target_index"] == 7
    assert role_act["text_value"].lower() == "admin"


