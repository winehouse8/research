# 1. 목적
- 신뢰성 있으면서 효율적인 코딩 에이전트를 만들고자함. 기본적으로는 spec - test case -test 가 양방향 추적성이 지원되면 좋다고 생각함. 이외에도 신뢰성 충족을 위해서는 여러 개발 방법론, 요구사항분석 기법들이 있는데, 해당 기법들을 참조해서 목적에 적합한 좋은 개발 방법론을 사용하고 싶음.

# 2. 조사 요구사항
1. Human in the loop
    - claude code 처럼 중간중간 사람이 필요한 단계에서는 사람과 같이 채팅하여 결정해야함. 신뢰성이 높은 코딩 에이전트를 만들기 위해서는 아직은 필요한 단계로 보임
2. 결정론적 동작(code) + 비결정론적 동작(agent)
- claude code와 같은 코딩 에이전트는 비결정론적인 동작을 보여주지만, 신뢰성 있는 코딩 에이전트를 위해서는 결정론적 동작을 섞고싶음. 이를 위해 결정론적인 상태머신 내 각 노드를 결정론적인 코드가되게할지, 비결정론적인 claude code 같은 one loop(n0) agent가 되게할지 선택하여 쓸 수 있음. 혹은 다른 방법으로는 Outer Loop 자체도 상태머신이 아닌 claude code 같은 one loop(n0) agent 를 쓰되, 이에 결정론적인 종작을 필요에 의해 섞고 싶을때 여러 이벤트에 HOOK을 걸어서 사용한다던지 할 수도 있어보임. 이에 대한 조사가 필요
- 이를 위해서는 customize가 Agent로 시작해서, 현재 프로젝트에 맞게 customize를 해서 쓸 수 있어야 함. claude code, PI 등등의 Human in the loop를 지원하는 소스중에 결정론적 동작(code) + 비결정론적 동작(agent) 을 어떻게 커스터마이징 해서 만들어낼지가 관건임.
- 아래 두 글에 영향을 받음
        - https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents
        - https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents-part-2
3. 신뢰성과 효율성은 trade-off 관계임. 모든 Agent를 langgraph방식의 상태머신으로 만든다면 신뢰성을 올라가지만, 해당 시스템이 처리할 수 있는 task가 적어지므로 효율성은 떨어짐. 이를 고려해서 둘다 챙긴 시스템을 만들어서 회사내부에 정착시키는것이 목표임.