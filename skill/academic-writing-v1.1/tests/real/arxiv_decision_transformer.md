# Decision Transformer: Reinforcement Learning via Sequence Modeling

## Abstract
We introduce a framework that abstracts Reinforcement Learning (RL) as a sequence modeling problem. This allows us to draw upon the simplicity and scalability of the Transformer architecture, and associated advances in language modeling such as GPT-x and BERT. In particular, we present Decision Transformer, an architecture that casts the problem of RL as conditional sequence modeling. Unlike prior approaches to RL that fit value functions or compute policy gradients, Decision Transformer simply outputs the optimal actions by leveraging a causally masked Transformer. By conditioning an autoregressive model on the desired return (reward), past states, and actions, our Decision Transformer model can generate future actions that achieve the desired return. Despite its simplicity, Decision Transformer matches or exceeds the performance of state-of-the-art model-free offline RL baselines on Atari, OpenAI Gym, and Key-to-Door tasks.

## References
[1] L. Chen, K. Lu, A. Rajeswaran, et al., "Decision transformer: Reinforcement learning via sequence modeling," in Proc. Adv. Neural Inf. Process. Syst., vol. 34, 2021, pp. 15084–15097.
