param name string
param managedEnvironmentId string
param image string
param role string
param externalIngress bool
param targetPort int = 8000
param minReplicas int
param maxReplicas int
@secure()
param cloudDatabaseUrl string
param truthPackUri string = ''
param truthPackHash string = ''
@secure()
param founderPassword string = ''
@secure()
param sessionSecret string = ''

var isApi = role == 'api'
var isWorker = role == 'worker'
var isScheduler = role == 'scheduler'

resource app 'Microsoft.App/containerApps@2023-05-01' = {
  name: name
  location: resourceGroup().location
  properties: {
    managedEnvironmentId: managedEnvironmentId
    configuration: union({
      secrets: concat([
        { name: 'cloud-database-url'; value: cloudDatabaseUrl }
      ], isApi ? [
        { name: 'founder-password'; value: founderPassword }
        { name: 'session-secret'; value: sessionSecret }
      ] : [])
    }, externalIngress ? {
      ingress: {
        external: true
        targetPort: targetPort
        transport: 'auto'
      }
    } : {})
    template: {
      containers: [
        {
          name: role
          image: image
          command: [ 'python', 'scripts/container_entrypoint.py', role ]
          env: concat([
            { name: 'CLOUD_DATABASE_URL'; secretRef: 'cloud-database-url' }
            { name: 'OPPORTUNITYOS_ENVIRONMENT'; value: 'cloud' }
          ], isApi ? [
            { name: 'OPPORTUNITYOS_FOUNDER_PASSWORD'; secretRef: 'founder-password' }
            { name: 'OPPORTUNITYOS_SESSION_SECRET'; secretRef: 'session-secret' }
            { name: 'OPPORTUNITYOS_TRUTH_PACK_URI'; value: truthPackUri }
            { name: 'OPPORTUNITYOS_TRUTH_PACK_HASH'; value: truthPackHash }
            { name: 'OPPORTUNITYOS_FORCE_SECURE_COOKIES'; value: '1' }
          ] : isWorker ? [
            { name: 'OPPORTUNITYOS_TRUTH_PACK_URI'; value: truthPackUri }
            { name: 'OPPORTUNITYOS_TRUTH_PACK_HASH'; value: truthPackHash }
          ] : [])
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}
