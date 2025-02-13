# X-Sample-CTL

## Python Environment
```bash
python -m venv venv
source venv/bin/activate  
pip install -r requirements.txt
```

## Organizing the Dataset

Create a `datasets/` directory at the root level and move `ImageNet-S-50` into it. The final structure should look like this:

<pre>
datasets/
└── ImageNet-S-50/ 
    └── train/
</pre>

To verify, run:

```bash
python test_dataset_setup.py
```

## Saving Checkpoints

Create a `checkpoints/` directory at the root level. 



