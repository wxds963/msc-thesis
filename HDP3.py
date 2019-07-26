import numpy as np
import tensorflow as tf
import tensorflow.keras.layers as kl
import tensorflow.keras.losses as kls
import tensorflow.keras.optimizers as ko
from plotting import plot_stats
import pandas as pd
from collections import deque
from heli_simple import SimpleHelicopter


class HDPAgentNumpy:

    def __init__(self, run_number=0):
        self.gamma = 0.95
        self.w_critic_input_to_hidden = np.random.rand(3, 6) * 1 / np.sqrt(6)
        self.w_critic_hidden_to_output = np.random.rand(6, 1) * 1 / np.sqrt(2)
        self.w_actor_input_to_hidden = np.random.rand(3, 6) * 1 / np.sqrt(6)
        self.w_actor_hidden_to_output = np.random.rand(6, 1)
        self.run_number = run_number

    def action(self, obs):

        a1 = np.matmul(obs[None, :], self.w_actor_input_to_hidden)
        h = np.tanh(a1)
        a2 = np.matmul(h, self.w_actor_hidden_to_output)
        return (np.deg2rad(10) * np.tanh(a2))[0][0]

    def train(self,
              env,
              n_episodes=500,
              n_updates=5):

        # training loop: collect samples, send to optimizer, repeat updates times
        episode_rewards = [0.0]

        wci = self.w_critic_input_to_hidden
        wco = self.w_critic_hidden_to_output
        wai = self.w_actor_input_to_hidden
        wao = self.w_actor_hidden_to_output


        # This is a property of the environment
        dst_da = env.get_environment_transition_function()

        def _critic(observation):
            c_hidden_in = np.matmul(observation[None, :], wci)
            hidden = np.tanh(c_hidden_in)
            value = np.matmul(hidden, wco)
            return value[0][0], hidden

        def _actor(observation):
            a_hidden_in = np.matmul(observation[None, :], wai)
            hidden = np.tanh(a_hidden_in)
            a_out_in = np.matmul(hidden, wao)
            action = np.deg2rad(10) * np.tanh(a_out_in)
            return action[0][0], hidden

        for n_episode in range(n_episodes):

            if (n_episode + 1) % 10 == 0:
                print("Update # " + str(n_episode + 1))
                self.test(env, render=True)

            # Initialize environment and tracking task
            observation = env.reset()
            stats = []
            learning_rate = 0.1
            weight_stats = []

            # Repeat (for each step t of an episode)
            for step in range(int(env.episode_ticks)):

                # 1. Obtain action from critic network using current knowledge
                action, hidden_action = _actor(observation)

                # 2. Obtain value estimate for current state
                # value, hidden_v = _critic(observation)

                # 3. Perform action, obtain next state and reward info
                next_observation, reward, done = env.step(action)

                td_target = reward + self.gamma * _critic(next_observation)[0]

                # Update models x times per timestep
                for j in range(n_updates):
                    # 4. Update critic: error is td_target - curent value estimate for current observation
                    v, hc = _critic(observation)
                    e_c = td_target - v

                    dEc_dec = e_c
                    dec_dV = -1
                    dV_dwc_ho = hc
                    dV_dwc_ih = wco * 1/2 * (1-hc**2).T * observation[None, :]

                    dEc_dwc_ho = dEc_dec * dec_dV * dV_dwc_ho
                    dEc_dwc_ih = dEc_dec * dec_dV * dV_dwc_ih

                    wci += learning_rate * -dEc_dwc_ih.T
                    wco += learning_rate * -dEc_dwc_ho.T

                    # 5. Update actor
                    # dEa_dwa = dEa_dea * dea_dst * dst_du * du_dwa   = V(S_t) * dV/ds * ds/da * da/dwa
                    #    get new value estimate for current observation with new critic weights
                    v, h = _critic(observation)
                    #  backpropagate value estimate through critic to input
                    dea_dst = wci @ (wco * 1/2 * (1-h**2).T)

                    #    get new action estimate with current actor weights
                    a, ha = _actor(observation)
                    #    backprop action through actor network
                    da_dwa_ho = np.deg2rad(10) * 1/2 * (1-a **2) * ha
                    da_dwa_ih = np.deg2rad(10) * 1/2 * (1-a**2) * wao * 1/2 * (1-ha**2).T * observation[None, :]

                    #    chain rule to get grad of actor error to actor weights
                    scale = v * (dst_da @ dea_dst)
                    dEa_dwa_ho = scale * da_dwa_ho.T
                    dEa_dwa_ih = scale * da_dwa_ih.T

                    #    update actor weights
                    wai += learning_rate * -dEa_dwa_ih
                    wao += -learning_rate * dEa_dwa_ho

                # 6. Save previous values
                stats.append({'t': env.task.t,
                              'r': reward,
                              'q': observation[0],
                              'q_ref': env.task.get_ref(),
                              'a1': observation[1],
                              'u': action})
                observation = next_observation
                weight_stats.append(np.concatenate([i.ravel() for i in [wci, wco, wai, wao]]))

                # Anneal learning rate (optional)
                learning_rate *= 0.9996

            #  Performance statistics
            episode_stats = pd.DataFrame(stats)
            episode_reward = episode_stats.r.sum()
            print("Cumulative reward episode:#" + str(self.run_number), episode_reward)
            plot_stats(episode_stats, 'Episode # ' + str(self.run_number) + ' | k_beta='+str(env.k_beta)+' | tau='+str(env.tau), True)

            #  Neural network weights over time:
            weights_history = pd.DataFrame(data=weight_stats,
                                           index=np.arange(0, env.max_episode_length, env.dt))


        return episode_reward

    def test(self, env, max_steps=None, render=True):
        obs, done, ep_reward = env.reset(), False, 0
        action=0
        stats = []

        while not done:
            stats.append({'t': env.task.t, 'q': obs[0], 'q_ref': env.task.get_q_ref(), 'a1': obs[1], 'u': action})
            action = self.action(obs)
            obs, reward, done = env.step(action)
            ep_reward += reward
            max_episode_length = env.max_episode_length if max_steps is None else max_steps

        if render:
            df = pd.DataFrame(stats)
            plot_stats(df, 'test', True)

        return ep_reward

if __name__ == '__main__':
    agent = HDPAgentNumpy()
