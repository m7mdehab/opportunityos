targetScope = 'resourceGroup'

@description('Existing Container Apps managed environment resource ID. No environment is created here.')
param existingManagedEnvironmentResourceId string
@description('Founder-stage application and job name prefix.')
param namePrefix string
@description('Immutable OCI image, preferably registry/repository@sha256:<64 hex>.')
param image string
@description('Private registry server for the immutable OCI image.')
param registryServer string = 'ghcr.io'
@description('Private registry username.')
param registryUsername string
@secure()
@description('Private registry pull token/password. Stored only as Container Apps secret.')
param registryPassword string
@secure()
param cloudDatabaseUrl string
@secure()
param founderPasswordHash string = ''
@secure()
param sessionSecret string = ''
param publicOrigin string
@secure()
param truthPackUri string
@secure()
param truthPackAuthToken string = ''
@secure()
param truthPackApiKey string = ''
param truthPackHash string
param deployApplicationRoles bool = true

module migrate 'modules/container-job.bicep' = {
  name: '${namePrefix}-migrate-job'
  params: {
    name: '${namePrefix}-migrate'
    managedEnvironmentId: existingManagedEnvironmentResourceId
    image: image
    registryServer: registryServer
    registryUsername: registryUsername
    registryPassword: registryPassword
    cloudDatabaseUrl: cloudDatabaseUrl
  }
}

module api 'modules/container-app.bicep' = if (deployApplicationRoles) {
  name: '${namePrefix}-api-app'
  params: {
    name: '${namePrefix}-api'
    managedEnvironmentId: existingManagedEnvironmentResourceId
    image: image
    role: 'api'
    externalIngress: true
    targetPort: 8000
    minReplicas: 1
    maxReplicas: 2
    cloudDatabaseUrl: cloudDatabaseUrl
    founderPasswordHash: founderPasswordHash
    sessionSecret: sessionSecret
    publicOrigin: publicOrigin
    truthPackUri: truthPackUri
    truthPackAuthToken: truthPackAuthToken
    truthPackApiKey: truthPackApiKey
    truthPackHash: truthPackHash
  }
}

module worker 'modules/container-app.bicep' = if (deployApplicationRoles) {
  name: '${namePrefix}-worker-app'
  params: {
    name: '${namePrefix}-worker'
    managedEnvironmentId: existingManagedEnvironmentResourceId
    image: image
    role: 'worker'
    externalIngress: false
    minReplicas: 1
    maxReplicas: 2
    cloudDatabaseUrl: cloudDatabaseUrl
    truthPackUri: truthPackUri
    truthPackAuthToken: truthPackAuthToken
    truthPackApiKey: truthPackApiKey
    truthPackHash: truthPackHash
  }
}

module scheduler 'modules/container-app.bicep' = if (deployApplicationRoles) {
  name: '${namePrefix}-scheduler-app'
  params: {
    name: '${namePrefix}-scheduler'
    managedEnvironmentId: existingManagedEnvironmentResourceId
    image: image
    role: 'scheduler'
    externalIngress: false
    minReplicas: 1
    maxReplicas: 1
    cloudDatabaseUrl: cloudDatabaseUrl
  }
}
