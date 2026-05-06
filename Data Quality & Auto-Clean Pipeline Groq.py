import pandas as pd
import sys
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq
import os

load_dotenv()

base_dir = Path(__file__).parent

def load_file(path):
    file_path = Path(path)

    if not file_path.is_absolute():
        file_path = base_dir / path

    if not file_path.exists():
        print(f'File not found: {file_path}')
        sys.exit()

    try:
        if path.endswith('.csv'):
            df = pd.read_csv(file_path)
        elif path.endswith('.json'):
            df = pd.read_json(file_path)
        elif path.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file_path)
        else:
            print('Unsupported file format')
            sys.exit()

    except Exception as e:
        print(f'Error loading file: {e}')
        sys.exit()

    if df.empty:
        print('File is empty')
        sys.exit()

    return df

def analyze_dataframe(df):
    numeric_df = df.select_dtypes('number')

    return {
        'rows': df.shape[0],
        'columns_quantity': df.shape[1],
        'columns_names': list(df.columns),
        'missing_values': df.isnull().sum().to_dict(),
        'duplicates': int(df.duplicated().sum()),
        'means': numeric_df.mean().to_dict(),
        'mins': numeric_df.min().to_dict(),
        'maxs': numeric_df.max().to_dict(),
    }

def analyze_and_decide(df):
    missing_values = False
    outlier_count = 0

    result = {
        'status': '',
        'problems': []
    }

    for col in df.select_dtypes('number').columns:
        if df[col].isna().any():
            missing_values = True
            result['problems'].append(f'Column {col} has missing values')

        if (df[col] > df[col].median() * 2).any():
            outlier_count += 1
            result['problems'].append(f'Column {col} has outliers')

    if missing_values or outlier_count >= 2:
        result['status'] = 'CRITICAL'
    elif outlier_count == 1:
        result['status'] = 'WARNING'
    else:
        result['status'] = 'OK'

    return result

def auto_fix(df):
    fixed_df = df.copy().reset_index(drop=True)
    result = {
        'fixed_df': fixed_df,
        'actions': []
    }

    for col in fixed_df.select_dtypes('number').columns:
        if fixed_df[col].isna().any():
            fixed_df[col] = fixed_df[col].fillna(fixed_df[col].median())
            result['actions'].append(f'filled missing values in {col}')

        
        if fixed_df[col].notna().any():
            median = float(fixed_df[col].median())
        else:
            continue    
        outlier_mask = fixed_df[col] > median * 2

        if outlier_mask.any():
            fixed_df.loc[outlier_mask, col] = median
            result['actions'].append(f'replaced outliers in {col}')

    return result

def format_report(data, df_condition, fix_report):
    means = '\n'.join([f'  mean {col}: {val:.2f}' for col, val in data['means'].items()])
    mins_maxs = '\n'.join([f'  min/max {col}: {data["mins"][col]} / {data["maxs"][col]}' for col in data['mins']])

    problems = '\n'.join([f'  - {p}' for p in df_condition['problems']]) or '  none'
    actions = '\n'.join([f'  - {a}' for a in fix_report['actions']]) or '  none'

    return f'''Status: {df_condition['status']}

Problems:
{problems}

Actions taken:
{actions}

rows: {data['rows']}
columns quantity: {data['columns_quantity']}
columns names: {data['columns_names']}

missing values: {data['missing_values']}
duplicates: {data['duplicates']}

{means}

{mins_maxs}'''

def ai_explain(report_text, df_condition, auto_fix):
    try:
        client = Groq(api_key=os.getenv('GROQ_API_KEY'))
        
        if len(report_text) > 2000:
            report_text = report_text.split('missing values')[0]

        prompt = f"""
    You are a data analyst.

    Explain this report in simple human language.
    Focus on:
    - what is wrong
    - why it matters
    - what should be done

    Report:
    {report_text}
    """
        
        response = client.chat.completions.create(
            model='llama-3.3-70b-versatile',
            messages=[{
                'role': 'user',
                'content': prompt
            }]
        )

        return response.choices[0].message.content

    
    except Exception as e:
        return f'AI error {e}'

def run_pipeline(path):
    df = load_file(path=path)

    data = analyze_dataframe(df=df)
    df_condition = analyze_and_decide(df=df)

    fix_report = {'actions': []}

    if df_condition['status'] != 'OK':
        fix_result = auto_fix(df=df)
        fix_report = fix_result
        fix_result['fixed_df'].to_csv(base_dir / 'fixed_data.csv', index=False)

    report_data = format_report(data=data, df_condition=df_condition, fix_report=fix_report)

    ai_explanation = ai_explain(report_text=report_data, df_condition=df_condition, auto_fix=fix_report)

    return {
        'report': report_data,
        'ai_explanation': ai_explanation,
        
    }

    
path = 'data.csv'
result = run_pipeline(path)

with open(base_dir / 'report.txt', 'w') as report:
    report.write(result['report'] + '\n\n' + result['ai_explanation'])

