# ShoeDLU

ShoeDLU is a grounded natural-language understanding system for a symbolic shoe-rack world. It compares three levels of language processing:

1. a rule-based parser,
2. a logistic-regression intent classifier combined with rule-based argument extraction, and
3. a logistic-regression intent classifier combined with a CRF-based slot tagger.

Each parser configuration can optionally be combined with a Hugging Face model checker using `Qwen/Qwen3-4B-Instruct-2507`.
All parser configurations produce a shared symbolic representation. The resulting frame is grounded against the current world state before the requested action is executed.

An interactive Gradio demo is provided in `notebooks/interactive_demo.ipynb`. It allows users to create random worlds, select a parser, optionally enable the Stage 3 model checker, execute commands, and inspect the resulting world state visually.



## Table of Contents

* [Installation](#installation)
* [Running the Project](#running-the-project)
  * [Interactive Demo](#interactive-demo)
  * [Hugging Face API Access](#hugging-face-api-access)
* [Repository Structure](#repository-structure)
  * [Directory Overview](#directory-overview)
* [Stage 1: Rule-Based Parser](#stage-1-rule-based-parser)
  * [Supported Intents](#supported-intents)
  * [Command Normalisation](#command-normalisation)
  * [Object and Attribute Parsing](#object-and-attribute-parsing)
  * [Separating Shoe and Tool Phrases](#separating-shoe-and-tool-phrases)
  * [Relation Parsing](#relation-parsing)
  * [Descriptive and Target Relations](#descriptive-and-target-relations)
  * [Example Symbolic Frame](#example-symbolic-frame)
  * [World Assumptions and Grounding](#world-assumptions-and-grounding)
  * [Effects of Actions on the World State](#effects-of-actions-on-the-world-state)
  * [Stage 1 Examples](#stage-1-examples)
* [Training the Stage 2 Models](#training-the-stage-2-models)
* [Evaluation and Reproducibility](#evaluation-and-reproducibility)
* [Report](#report)




## Installation


### 1. Clone the repository

```
git clone https://github.com/Annemarie-Weise/ShoeDLU.git
cd path/to/ShoeDLU
```

### 2. Create a virtual environment

The project was tested with Python 3.13.

Using Conda:
```
conda create -n shoedlu python=3.13 pip -y
conda activate shoedlu
```

Alternatively, using `venv`:
```
python3 -m venv .venv
source .venv/bin/activate
```

On Windows, activate the `venv` environment with:
```
.venv\Scripts\activate
```

### 3. Install the dependencies

Install the tested project dependencies from the repository root:
```
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The optional `requirements-lock.txt` file contains the complete package snapshot of the environment used during final testing.
To verify that the installed dependencies are consistent, run:
```
python -m pip check
```




## Running the Project

The notebooks are the main access point to the system. Use `notebooks/interactive_demo.ipynb` for the interactive application and `notebooks/demo.ipynb` for the compact Stage 1 command examples.

Activate the project environment and start JupyterLab from the project root:
```
conda activate shoedlu
jupyter lab
```

Alternatively, JupyterLab can be started directly from the `notebooks/` directory:
```
cd notebooks
jupyter lab
```

The notebooks automatically locate the project root in both cases. Make sure that the selected notebook kernel uses the environment in which the project dependencies were installed.
The training scripts are documented separately and do not need to be executed in order to run the system with the supplied trained models.


### Interactive Demo

The interactive Gradio application is provided in:
```
notebooks/interactive_demo.ipynb
```
Run the notebook from top to bottom to launch the application in the default web browser. The demo allows users to generate random worlds, select one of the three parsers, execute natural-language commands, and inspect the resulting dialogue and world state. The optional Stage 3 model checker can be enabled when a Hugging Face token is available (the notebook asks for the token if no HF_TOKEN environment variable is found).


### Hugging Face API Access

The notebooks include configurations that use the optional Stage 3 model checker with `Qwen/Qwen3-4B-Instruct-2507`.

The rule-based demo does not require Hugging Face API access. The quantitative and qualitative evaluation notebook check for a token in the HF_TOKEN environment variable and ask for one if the environment variable is not set.

Hugging Face Inference Providers apply account-dependent usage limits and inference credits. A free account is generally sufficient for running the demo and testing a small number of commands. However, the complete quantitative evaluation sends considerably more API requests and may exceed the available free allowance.

If the available credits or request limits are exhausted, Stage 3 requests may return API errors. These errors do not prevent the symbolic and statistical components from running, but they may affect configurations in which a Stage 3 correction would otherwise have been attempted. Reproducing the complete Stage 3 evaluation may therefore require additional inference credits or an appropriate paid account. Hugging Face pricing, included credits, and usage limits may change over time, so users should check the current conditions in their Hugging Face account before running the full evaluation.

The project uses remote inference because the computational resources required to run the selected language model locally were not available during development.




## Repository structure

```
ShoeDLU/
├── Assignment_report.pdf
├── requirements.txt
├── requirements-lock.txt
├── data/
│   ├── evaluation_data/
│   └── model_training_data/
├── evaluation_results/
│   ├── model_training_logs/
│   └── end_to_end_results/
├── models/
├── notebooks/
│   ├── qualitative_evaluation_examples.ipynb
│   ├── quantitative_evaluation_testing.ipynb
│   ├── interactive_demo.ipynb
│   └── demo.ipynb
└── src/
    ├── dialogue/
    ├── grounding/
    ├── parsers/
    │   └── training_stage2/
    │       ├── train_intent_classifier.py
    │       └── train_slot_tagger.py
    ├── stage3/
    ├── domain_rules_and_constants.py
    └── world.py
```


### Directory Overview

* `data/evaluation_data/` contains the commands and scenarios used for quantitative and qualitative evaluation.
* `data/model_training_data/` contains the training datasets, data-generation prompts, and preprocessing scripts used to prepare the intent-classification and BIO slot-tagging data.
* `models/` contains the trained intent-classification and CRF slot-tagging models.
* `notebooks/` contains the interactive demo and the qualitative and quantitative evaluation notebooks.
* `evaluation_results/` contains saved predictions, metrics, and evaluation outputs for the model training and the end-to-end evaluation.
* `src/` contains the implementation of the parsers, grounding, dialogue manager, symbolic shoe world, domain rules, and the optional Stage 3 model checker as well as the training scripts for the stage 2 models.




## Stage 1: Rule-Based Parser

Stage 1 implements a deterministic rule-based language-understanding system for the symbolic shoe-rack world. It does not require trained models or Hugging Face API access. it is implementedby the `RuleBasedParser` class.

The parser converts a natural-language command into a symbolic semantic frame. This frame contains the detected intent, symbolic object descriptions, action parameters, and relational constraints. The parser itself does not select concrete world objects. The resulting references are resolved against the current world state in a separate grounding step.


### Supported Intents

The system supports nine intents:

| Intent | Expected information |
| - | - |
| `PICK_UP` | A description of the object to pick up |
| `PUT_DOWN` | A description of the currently held object (optional) and a target location or `next_to` target |
| `MOVE`| A description of the object to move and a target location or `next_to` target |
| `CLEAN` | A description of the shoe and a description of the cleaning utensil which should be used |
| `DRY` | A description of the shoe |
| `IMPREGNATE` | A description of the shoe and a description of the impregnation utensil which should be used |
| `REPAIR` | A description of the shoe, an optional repair part, and a description of the repair tool  which should be used |
| `GO_ON_WALK` | A description of the shoe and optional walk length, place, and weather condition |
| `GET_NEW_TOOL` | The type of cleaning, impregnation, or repair tool to create |

Intent detection is based on regular-expression patterns and predefined action aliases. For example, `grab` and `take` map to `PICK_UP`, `wash` maps to `CLEAN`, and `fix` maps to `REPAIR`.
The first matching intent pattern is selected. The matched action expression is then removed before the remaining command is parsed. This prevents words such as `dry` from being interpreted both as an action and as a shoe attribute. The intent determines which action is requested and which arguments the parser must extract. The parser itself only creates a symbolic frame. After the references have been grounded, the corresponding world action is executed and may update object locations, shoe attributes, or tool states.


### Command Normalisation

Before parsing, the command is:

1. converted to lowercase,
2. stripped of sentence punctuation,
3. normalised to use single spaces, and
4. mapped from linguistic aliases to canonical world values.

For example:
```
trainers -> sneaker
tan  -> brown
cloth  -> rag
waterproofing spray -> spray
lower shelf -> bottom_shelf
```

The symbolic frame therefore uses the same canonical vocabulary as the world and grounding components.


### Object and Attribute Parsing

The world contains four object classes:

* `shoe`
* `cleaning_utensil`
* `impregnation_utensil`
* `repair_tool`

For generic object commands such as `PICK_UP`, `PUT_DOWN`, and `MOVE`, the parser attempts to identify the object class from the vocabulary in the object phrase. It checks for cleaning utensils, impregnation utensils, repair tools, and shoes. The first class with recognised attributes is used.

If no object class or attributes can be extracted, the original phrase is retained. This allows the grounding component to resolve explicit world-object identifiers such as `boot_1` or `cleaner_2`.

A shoe description can contain the following attributes:

* type: `boot`, `sneaker`, or `sandal`
* height: `high`, `mid`, or `low`
* colour
* material
* cleaning status
* dirt type
* impregnation status
* dry status
* sole status
* material status

For example:
```
the wet black canvas boot
```
is converted into filters equivalent to:
```
shoe_type: boot
color: black
material: canvas
dry_status: wet
```

A cleaning-utensil description can contain the following attributes:

* type: `cleaner`, `rag`, or `brush`
* exact fullness percentage
* minimum required fullness percentage

For example:
```
the brush that is 34% full
```
is converted into filters equivalent to:
```
utensil_type: brush
fullness_percent: 34
```

A minimum fullness requirement can also be expressed:
```
the rag with at least 30% remaining
```
which produces filters equivalent to:
```
utensil_type: rag
min_fullness: 30
```

An impregnation-utensil description can contain the following attributes:

* type: `spray` or `cream`
* exact fullness percentage
* minimum required fullness percentage

For example:
```
the spray that is at least 40% full
```
is converted into filters equivalent to:
```
utensil_type: spray
min_fullness: 40
```

A repair-tool description can contain the following attributes:

* type: `needle_and_yarn`, `sole_glue`, or `sole_hammer`
* exact damage percentage
* maximum permitted damage percentage

For example:
```
the hammer that is 15% damaged
```
is converted into filters equivalent to:
```
tool_type: sole_hammer
damage_status: 15
```

A maximum damage constraint can also be expressed:
```
the needle with at most 20% damage
```
which produces filters equivalent to:
```
tool_type: needle_and_yarn
max_damage: 20
```

Common linguistic variants are mapped to the canonical tool types before the filters are created. For example, `cloth` is mapped to `rag`, `waterproofing spray` to `spray`, `glue` to `sole_glue`, and `hammer` to `sole_hammer`.

The complete lists of supported attribute values and linguistic aliases are provided in `src/domain_rules_and_constants.py`.


### Separating Shoe and Tool Phrases

Commands for `CLEAN`, `IMPREGNATE`, and `REPAIR` normally contain both a shoe and a tool. The rule-based parser splits these commands at the first occurrence of:
```
with
using
by using
```

The phrase before the separator is assigned to the shoe role, while the phrase after it is assigned to the utensil or repair-tool role.
For example:
```
clean the white rubber sneaker with the brush
```
is split into:
```
Shoe phrase: the white rubber sneaker
Tool phrase: the brush
```

Each part is then processed with its own role-specific vocabulary. If no separator is present, both role parsers inspect the complete command and extract only the attributes belonging to their expected object class.
Repair commands additionally identify whether the command refers to the shoe’s `sole` or `material`. Expressions such as `surface`, `fabric`, or `upper` are normalised to `material`, while `underside` is normalised to `sole`.


### Relation Parsing

The parser supports three canonical relations:
* `on`, used for objects on shelves
* `inside`, used for objects in areas such as the floor box or drying area
* `next_to`, used for spatial references to another object

Recognised formulations include:
```
on, onto, on top of
inside, within, into
next to, right next to, beside
```

For descriptive references, expressions such as `from`, `off`, and `off of` are also interpreted as references to an object located on a shelf.
Relations are extracted separately from the main object attributes. The object phrase is cut at the first relevant relation before its attributes are parsed. This prevents attributes belonging to a relation target from being assigned to the main object.

For example:
```
the white sneaker next to the red sandal
```
produces a white sneaker as the main object and a red sandal as the target of its `next_to` relation.

A location relation can also be inferred from a recognised location when no explicit relation expression is present. Shelf locations are represented with `on`, while the floor box, drying area, tool area, and hand are represented with `inside`.


### Descriptive and Target Relations

The parser distinguishes between two functions of a relation:
* A **descriptive relation** restricts which object is being referred to.
* A **target relation** specifies where an action should place an object.

For `MOVE`, the last recognised relation is normally interpreted as the action target. Earlier relations describe the object being moved.
For example:
```
move the sneaker inside the floor box to the middle shelf
```
uses `inside the floor box` to identify the sneaker and `middle shelf` as the movement target.

For `PUT_DOWN`, the object is assumed to be held already. A `next_to` relation is therefore interpreted as a target relation rather than as a description of the held object. If a `next_to` relation is present, it takes priority over location relations. Otherwise, the first recognised location relation is used as the target.

Descriptive relations can be nested. For example:
```
the sneaker next to the boot on the top shelf
```
is represented as:
```text
sneaker
└── next_to
    └── boot
        └── on top_shelf
```
The top-shelf constraint therefore applies to the boot, not to the sneaker.


### Example Symbolic Frame

For the command:
```
clean the white rubber sneaker next to the red rubber sandal with the brush that is 34% full
```
the rule-based parser produces a frame equivalent to:
```
{
  "intent": "CLEAN",
  "shoe_ref": {
    "object_class": "shoe",
    "filters": {
      "shoe_type": "sneaker",
      "color": "white",
      "material": "rubber"
    },
    "object_phrase": "the white rubber sneaker",
    "relation_refs": [
      {
        "relation_type": "next_to",
        "target_ref": {
          "object_class": "shoe",
          "filters": {
            "shoe_type": "sandal",
            "color": "red",
            "material": "rubber"
          },
          "object_phrase": "the red rubber sandal",
          "relation_refs": []
        },
        "target_phrase": "the red rubber sandal"
      }
    ]
  },
  "utensil_ref": {
    "object_class": "cleaning_utensil",
    "filters": {
      "utensil_type": "brush",
      "fullness_percent": 34
    },
    "object_phrase": "the brush that is 34% full",
    "relation_refs": []
  }
}
```

This frame still contains symbolic descriptions rather than concrete object identifiers.


### World Assumptions and Grounding

The symbolic world contains shoes, cleaning utensils, impregnation utensils, and repair tools. Objects may be located on three ordered shelves, inside the floor box, in the drying area, in the tool area, or in the agent’s hand.

The main spatial assumptions are:
* the top, middle, and bottom shelves contain ordered slots
* two shelf objects are `next_to` each other only when they occupy adjacent slots
* the floor box, drying area, and tool area are unordered
* all objects in the same unordered area are treated as mutually `next_to`
* the agent can hold at most one object
* shoes can only be placed in locations permitted for their height (and they never fit in the tool box)
* shelf capacity and available adjacent slots are checked during execution.

The grounding component first checks whether an explicit object identifier occurs in the original phrase. Otherwise, it filters the current world objects by object class, canonical attributes, and recursive relation constraints.

Grounding returns one of the following states:
* `UNIQUE_MATCH`: exactly one object satisfies the description
* `AMBIGUOUS`: several objects satisfy the description
* `NO_MATCH`: no object satisfies the description
* `INVALID_ID`: an identifier-like expression does not exist in the world

The resolver never chooses an arbitrary candidate from an ambiguous result. A command may therefore be parsed successfully but still remain ambiguous, produce no match, or fail during execution because of a world constraint.


### Effects of Actions on the World State

Executing an intent can change the state of the symbolic world. The exact effect depends on the selected shoe or tool, its current attributes, and the applicable domain rules.

| Intent| Main effects |
| - | - |
| `PICK_UP` | Moves the selected object into the agent's hand. The agent can hold at most one object. |
| `PUT_DOWN` | Moves the held object to a specified location or places it next to another object. |
| `MOVE` | Changes an object's location. Moving a shoe to the drying area also changes its `dry_status` to `dry`. |
| `CLEAN` | Improves the shoe's `cleaning_status`. If the shoe becomes fully clean, its `dirt_type` is removed. The cleaning utensil loses fullness, and some utensil types can damage the shoe material. |
| `DRY` | Moves the shoe to the drying area and changes its `dry_status` to `dry`. |
| `IMPREGNATE` | Improves the shoe's `impregnation_status` and reduces the utensil's fullness. The effect is reduced when the shoe is wet. |
| `REPAIR` | Improves the requested `sole_status`, `material_status`, or both. Using the repair tool increases its `damage_status`. |
| `GO_ON_WALK` | Makes the shoe dirtier, assigns a `dirt_type` based on the walk location, and may worsen its sole and material condition. Weather affects the shoe's dry and impregnation states. |
| `GET_NEW_TOOL` | Creates a new tool in the tool area. Cleaning and impregnation utensils are created with 100% fullness, while repair tools are created with 0% damage. |

The individual tools do not have identical effects:
* `cleaner` provides the strongest general cleaning effect but changes the shoe's `material_status` to `cracked` and loses 5% fullness per use.
* `rag` provides a smaller cleaning effect, works particularly well on mud and oil, does not damage the material, and loses 3% fullness per use.
* `brush` works particularly well on grass, sand, and dust, worsens the material condition by one level, and loses 2% fullness per use.
* `spray` improves impregnation by one level and loses 5% fullness per use.
* `cream` improves impregnation by two levels and loses 10% fullness per use.
* `needle_and_yarn` repairs the sole by one level and increases its own damage by 10%. It is also the only tool that can repair shoe-material damage.
* `sole_glue` repairs the sole by two levels and increases its own damage by 5%, but it has no effect on a wet shoe.
* `sole_hammer` repairs the sole by three levels and increases its own damage by 1%.

A cleaning or impregnation utensil is removed from the world when its fullness reaches 0%. A repair tool is removed when its damage reaches 100%.

Walk effects depend on the shoe type, walk length, location, and weather. Longer walks cause greater deterioration. The location determines the new dirt type, for example `grass` in a park, `sand` at a beach, or `mud` in a forest. Sunny weather makes the shoe dry. Rainy weather makes it wet, and a medium or long rainy walk also worsens its impregnation status by one level.

The complete action rules, status levels, supported values, and interaction effects are defined in `src/domain_rules_and_constants.py`. The execution logic that applies these rules is implemented in `src/world.py`.


### Stage 1 Examples

The Stage 1 examples are provided in:

```
notebooks/demo.ipynb
```
The demo notebook provides 15 example commands for the RuleBasedParser configuration and displays the system and world action outputs.


## Training the Stage 2 Models

Stage 2 introduces statistical models for intent classification and slot tagging.

The project uses:
* a logistic-regression classifier for intent prediction and
* a CRF-based sequence tagger for extracting BIO-labelled argument spans.

The same intent classifier is used in both statistical parser configurations:
1. intent classification combined with rule-based argument extraction and
2. intent classification combined with CRF-based slot extraction.

The repository already contains the trained model files in `models/`. Retraining is therefore optional and is only required when reproducing the training process.


### Training Data

The training resources are stored in:
```
data/model_training_data/
```
They include:
* 1,730 commands for intent classification
* 16,836 BIO-labelled token rows for slot tagging
* the prompts used to generate the initial examples
* preprocessing and formatting scripts used to prepare the final datasets

The datasets are split into 75% training data and 25% test data using the fixed random seed `404`.


### Training the Intent Classifier

Run the following command from the project root:
```
python -m src.parsers.training_stage2.train_intent_classifier
```
The script trains and evaluates the logistic-regression intent classifier. The trained model is written to `models/`, while the corresponding metrics and training outputs are stored under `evaluation_results/`.


### Training the CRF Slot Tagger

Run the following command from the project root:

```
python -m src.parsers.training_stage2.train_slot_tagger
```

The script trains and evaluates the CRF-based slot tagger on BIO-labelled token sequences. The resulting model is stored in `models/`, and the training metrics are written under `evaluation_results/`.
The training scripts must be started as Python modules from the project root so that the `src` package and the relative data, model, and result paths are resolved correctly.



## Evaluation and Reproducibility

The repository contains notebooks for qualitative inspection, quantitative evaluation, and interactive demonstration.


### Evaluation Notebooks

The qualitative evaluation is provided in:
```
notebooks/qualitative_evaluation_examples.ipynb
```
It presents selected commands together with their system messages and action results.

The quantitative evaluation is provided in:
```
notebooks/quantitative_evaluation_testing.ipynb
```
It evaluates the six parser configurations:
* rule-based parser
* rule-based parser with Stage 3
* intent classifier with rule-based argument extraction
* intent classifier with rule-based argument extraction and Stage 3
* intent classifier with CRF slot tagging
* intent classifier with CRF slot tagging and Stage 3

The evaluation uses 70 scenarios and reports:
* intent accuracy
* frame accuracy
* resolution accuracy
* execution accuracy
* end-to-end accuracy

The symbolic evaluation world is initialised using the fixed seed `205`.


### Reproducing the Results

For the closest reproduction of the submitted results:
1. create the environment using `requirements.txt` or `requirements-lock.txt`
2. use the supplied trained models from `models/`
3. run the evaluation notebooks from top to bottom
4. keep the provided datasets and fixed random seeds unchanged

The saved training metrics, predictions, and end-to-end evaluation outputs are available under:

```
evaluation_results/
```

The included Stage 2 models were trained with the dependency versions specified in the requirements files. In particular, the pinned `scikit-learn` version should be used when loading the supplied intent-classification model.

Runs without Stage 3 are expected to be reproducible when the same data, models, dependency versions, and seeds are used.

Stage 3 relies on remote Hugging Face inference. Its results may be affected by API availability and behavior. The saved Stage 3 results therefore represent the submitted evaluation run, while a later rerun may not be completely identical.

A complete quantitative evaluation takes approximately ten minutes in the tested environment, with most of the runtime caused by the external Stage 3 API requests.




## Report

The complete project report is provided in:
```
Assignment_report.pdf
```

The report explains the system architecture and the design of the symbolic world. It describes the Stage 2 training methodology, the Stage 3 model-checking approach, and the experimental setup. It also presents the quantitative results, qualitative error analysis, and a discussion of how the world representation affects system performance.

