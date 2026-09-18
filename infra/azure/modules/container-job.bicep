param name string
param managedEnvironmentId string
param image string
@secure()
param cloudDatabaseUrl string

resource job 'Microsoft.App/jobs@2023-05-01' = {
  name: name
  location: resourceGroup().location
  properties: {
    environmentId: managedEnvironmentId
    configuration: {
      triggerType: 'Manual'
      manualTriggerConfig: {
        replicaCompletionCount: 1
        parallelism: 1
      }
      replicaRetryLimit: 0
      replicaTimeout: 1800
      secrets: [
        { name: 'cloud-database-url'; value: cloudDatabaseUrl }
      ]
    }
    template: {
      containers: [
        {
          name: 'migrate'
          image: image
          command: [ 'python', 'scripts/container_entrypoint.py', 'migrate' ]
          env: [
            { name: 'CLOUD_DATABASE_URL'; secretRef: 'cloud-database-url' }
            { name: 'OPPORTUNITYOS_ENVIRONMENT'; value: 'cloud' }
          ]
        }
      ]
      initContainers: []
    }
  }
}
