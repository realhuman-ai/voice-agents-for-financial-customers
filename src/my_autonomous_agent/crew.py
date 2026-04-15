from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task
from crewai.agents.agent_builder.base_agent import BaseAgent
import os
from dotenv import load_dotenv
from my_autonomous_agent.tools.custom_tool import file_write_tool
from crewai_tools import SerperDevTool

# This forces the .env file to load into your system variables
load_dotenv() 

# Verification (Optional: delete after it works)
if not os.getenv("OPENAI_API_KEY"):
    print("CRITICAL ERROR: OPENAI_API_KEY not found in environment!")
# If you want to run a snippet of code before or after the crew starts,
# you can use the @before_kickoff and @after_kickoff decorators
# https://docs.crewai.com/concepts/crews#example-crew-class-with-decorators

@CrewBase
class MyAutonomousAgent():
    """MyAutonomousAgent crew"""
    search_tool = SerperDevTool()

    agents: list[BaseAgent]
    tasks: list[Task]

    @property
    def openai_llm(self) -> LLM:
        return LLM(model=os.getenv("MODEL", "gpt-4o"), temperature=0.7)

    # Learn more about YAML configuration files here:
    # Agents: https://docs.crewai.com/concepts/agents#yaml-configuration-recommended
    # Tasks: https://docs.crewai.com/concepts/tasks#yaml-configuration-recommended
    
    # If you would like to add tools to your agents, you can learn more about it here:
    # https://docs.crewai.com/concepts/agents#agent-tools
    @agent
    def researcher(self) -> Agent:
        return Agent(
            #config=self.agents_config['researcher'],
            #llm=self.openai_llm,
            #tools=[self.search_tool], # Adding your custom tool here
            #verbose=True
            ##
            #config=self.agents_config['manager_agent'],
            #llm=self.openai_llm,
            #allow_delegation=True, # MUST be True
            #verbose=True
            config=self.agents_config['researcher'],
            llm=self.openai_llm,
            tools=[self.search_tool, file_write_tool], # Researcher handles the "doing"
            allow_delegation=False,
            verbose=True
            
        )

    @agent
    def reporting_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config['reporting_analyst'], # type: ignore[index]
            verbose=True
        )
    @agent
    def manager_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['manager_agent'],
            llm=self.openai_llm,
            tools=[self.search_tool, file_write_tool],
            allow_delegation=True,
            verbose=True
        )
    # To learn more about structured task outputs,
    # task dependencies, and task callbacks, check out the documentation:
    # https://docs.crewai.com/concepts/tasks#overview-of-a-task
    @task
    def main_mission(self) -> Task:
        return Task(
            config=self.tasks_config['main_mission'], # type: ignore[index]
            output_file='report.md'
        )

    @crew
    def crew(self) -> Crew:
        """Creates the MyAutonomousAgent crew"""
        # To learn how to add knowledge sources to your crew, check out the documentation:
        # https://docs.crewai.com/concepts/knowledge#what-is-knowledge

        return Crew(
            agents=self.agents, # Automatically created by the @agent decorator
            tasks=self.tasks, # Automatically created by the @task decorator
           # process=Process.sequential,
            process=Process.hierarchical, # This enables a Manager agent to orchestrate
            manager_llm=LLM(model=os.getenv("MODEL", "gpt-4o"), temperature=0.7),
            verbose=True,
           # process=Process.hierarchical, # In case you wanna use that instead https://docs.crewai.com/how-to/Hierarchical/
        )
