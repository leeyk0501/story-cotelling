import os
import json
import random
import warnings
import logging
import argparse
import torch
import numpy as np
import pandas as pd
from dqn import DQN, DQNAgent, DQNTrainer
from environment.graph import KnowledgeGraph
from environment.chatenv import StoryBotRetellEnv

# set logging format
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# set the hyperparameters
parser = argparse.ArgumentParser()
parser.add_argument("-s", "--seed", help="random seed", type=int, default=42)
parser.add_argument("-c", "--cuda", help="cuda device", type=int, default=0, choices=[0, 1, 2])
parser.add_argument("-m", "--model1", help="load dqn model1 name", type=str, default='model/dqn1.pth')
parser.add_argument("-l", "--model2", help="load dqn model2 name", type=str, default='model/dqn2.pth')
parser.add_argument("-u", "--summary", help="story summary file", type=str, default="data/summary/summary_train.json")
parser.add_argument("-k", "--kg", help="story knowledge graph folder", type=str, default="knowledge_graph/data/kg/new_train")
args = parser.parse_args()

# set the hyperparameters
SEED = int(args.seed)
CUDA = args.cuda
DQN1 = args.model1
DQN2 = args.model2
SUMMARY = args.summary
KG = args.kg


# show the hyperparameters
logging.info(f'seed: {SEED}')
logging.info(f'cuda: {CUDA}')
logging.info(f'dqn1: {DQN1}')
logging.info(f'dqn2: {DQN2}')
logging.info(f'summary: {SUMMARY}')
logging.info(f'kg: {KG}')


# setting the seed
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)
torch.cuda.manual_seed_all(SEED)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False

# set the cuda device
device = torch.device(f'cuda:{args.cuda}' if torch.cuda.is_available() else 'cpu')

# ignore the warning
warnings.filterwarnings('ignore')

# load the story summary dataset
story_summary_dataset = {}
with open('data/summary/summary_train.json', 'r', encoding='utf8') as f:
    story_summary_dataset = {**story_summary_dataset, **json.load(f)}

# create the environment 1
env1 = StoryBotRetellEnv(story_summary_dataset,
                         reward_model_ckpt='environment/reward/model/ranking_model_best_c.pt', 
                         kg2text_model_ckpt='environment/kg2text/model/kg2text_model.pt', 
                         embedding_model_name='sentence-transformers/all-MiniLM-L6-v2', 
                         device=device)
env1.bot_name = 'agent1'
env1.user_name = 'agent2'

# create the environment 2
env2 = StoryBotRetellEnv(story_summary_dataset,
                         reward_model_ckpt='environment/reward/model/ranking_model_best_c.pt', 
                         kg2text_model_ckpt='environment/kg2text/model/kg2text_model.pt', 
                         embedding_model_name='sentence-transformers/all-MiniLM-L6-v2', 
                         device=device)
env2.bot_name = 'agent2'
env2.user_name = 'agent1'

# load the knowledge graph
story_name_list = list(story_summary_dataset.keys())
story_kg_path = 'data/kg/new_train'
kg_dict = {}
for story_name in story_name_list:
    kg = KnowledgeGraph(device=env1.embedding_model_device,
                        model=env1.embedding_model,
                        tokenizer=env1.embedding_tokenizer,
                        story_kg_file=os.path.join(story_kg_path, story_name+'.json'))
    kg_dict[story_name] = kg

# set the agent1
agent1 = DQNAgent(env=env1, epsilon=0.0)
agent1.load(DQN1)

# set the agent2
agent2 = DQNAgent(env=env2, epsilon=0.0)
agent2.load(DQN2)


df1 = pd.DataFrame()
df2 = pd.DataFrame()

score1_list = []
score2_list = []

for current_story_name in story_name_list:
    logging.info(f'current story name: {current_story_name}')
    current_kg = kg_dict[current_story_name]
    env1.reset(story_name=current_story_name, story_kg=current_kg)
    env2.reset(story_name=current_story_name, story_kg=current_kg)

    output_dialogue2 = ''
    output_kg2 = None

    while True:
        # two agent talk with each other
        env1.render(input_sentence=output_dialogue2, input_kg=output_kg2)
        done1, done1_msg = env1.done()
        if not done1:
            state1 = env1.observation()
            state1 = torch.tensor(state1, dtype=torch.float32).unsqueeze(0)
            action1 = agent1.act(state1)
            output_dialogue1, output_kg1 = env1.step(action1)
            next_state1 = env1.observation()
            reward1, score1 = env1.reward()
            done1, done1_msg = env1.done()
            # agent1.remember(state1, action1, reward1, next_state1, done1)

        if done1:
            break
        
        env2.render(input_sentence=output_dialogue1, input_kg=output_kg1)
        done2, done2_msg = env2.done()
        if not done2:
            state2 = env2.observation()
            state2 = torch.tensor(state2, dtype=torch.float32).unsqueeze(0)
            action2 = agent1.act(state1)
            output_dialogue2, output_kg2 = env2.step(action2)
            next_state2 = env2.observation()
            reward2, score2 = env2.reward()
            done2, done2_msg = env2.done()
            # agent2.remember(state2, action2, reward2, next_state2, done2)

        if done2:
            break

    score1_list.append(score1)
    score2_list.append(score2)

    # append df
    # TODO: kg to sen_idx
    df1 = df1.append(env1.dialogue_log_list, ignore_index=True)
    df2 = df2.append(env2.dialogue_log_list, ignore_index=True)
    df1.to_csv('dialogue_history_1.csv', index=False)
    df2.to_csv('dialogue_history_2.csv', index=False)

print('agent1 score: ', np.mean(score1_list))
print('agent2 score: ', np.mean(score2_list))