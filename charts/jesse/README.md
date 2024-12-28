# jesse

![Version: 0.0.1](https://img.shields.io/badge/Version-0.0.1-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: latest](https://img.shields.io/badge/AppVersion-latest-informational?style=flat-square)

A Helm chart for Jesse trade bot

**Homepage:** <https://jesse.trade/>

## Maintainers

| Name | Email | Url |
| ---- | ------ | --- |
| edu-diaz | <edudiazasencio@gmail.com> | <https://edudiaz.trianalab.net> |
| saleh-mir | <saleh@jesse.trade> | <https://jesse.trade/> |

## Source Code

* <https://github.com/jesse-ai/jesse>
* <https://github.com/jesse-ai/project-template>

## Requirements

| Repository | Name | Version |
|------------|------|---------|
| https://charts.bitnami.com/bitnami | postgresql | 16.3.3 |
| https://charts.bitnami.com/bitnami | redis | 20.6.1 |

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| affinity | object | `{}` | affinity expands nodeSelectors, more information can be found [here](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/#affinity-and-anti-affinity). |
| autoscaling.enabled | bool | `false` | autoscaling.enabled is for enabling horizontal autoscaling, more information can be found [here](https://kubernetes.io/docs/concepts/workloads/autoscaling/) |
| autoscaling.maxReplicas | int | `10` | autoscaling.maxReplicas sets the maximum number of replicas. |
| autoscaling.minReplicas | int | `1` | autoscaling.minReplicas sets the minimum number of replicas. |
| autoscaling.targetCPUUtilizationPercentage | int | `80` | autoscaling.targetCPUUtilizationPercentage sets CPU threshold that triggers the autoscaling. |
| config | string | `"PASSWORD=test\nAPP_PORT=9000\n\nPOSTGRES_HOST=postgresql\nPOSTGRES_NAME=jesse_db\nPOSTGRES_PORT=5432\nPOSTGRES_USERNAME=jesse_user\nPOSTGRES_PASSWORD=pg-password\n\nREDIS_HOST=redis-master\nREDIS_PORT=6379\nREDIS_PASSWORD=redis-password\n\nLICENSE_API_TOKEN=<MY_TOKEN>"` | config contains all the configuration variables for Jesse, more information can be found [here](https://docs.jesse.trade/docs/configuration#environment-variables). |
| fullnameOverride | string | `""` | fullnameOverride is to fully override the chart name. |
| image.command | string | `""` | image.command overrides the default command to run in the jesse container. |
| image.pullPolicy | string | `"IfNotPresent"` | image.pullPolicy sets the pull policy for images. |
| image.repository | string | `"salehmir/jesse"` | image.repository sets the container image more information can be found [here](https://kubernetes.io/docs/concepts/containers/images/). |
| image.tag | string | `""` | image.tag overrides the image tag whose default is the chart appVersion. |
| imagePullSecrets | list | `[]` | imagePullSecrets is for the secretes for pulling an image from a private repository more information can be found [here](https://kubernetes.io/docs/tasks/configure-pod-container/pull-image-private-registry/). |
| ingress.annotations | object | `{}` | ingress.annotations is for setting Kubernetes Annotations to the Ingress, more information can be found [here](https://kubernetes.io/docs/concepts/overview/working-with-objects/annotations/). |
| ingress.className | string | `""` | ingress.className sets the ingress class, more information can be found [here](https://kubernetes.io/docs/concepts/services-networking/ingress/#ingress-class). |
| ingress.enabled | bool | `false` | ingress.enabled is for setting up the ingress, more information can be found [here](https://kubernetes.io/docs/concepts/services-networking/ingress/). |
| ingress.hosts | list | `[]` | ingress.hosts is a list of ingress hosts. |
| ingress.tls | list | `[]` | ingress.tls is the secret holding the TLS key and secret, more information can be found [here](https://kubernetes.io/docs/concepts/services-networking/ingress/#tls). |
| nameOverride | string | `""` | nameOverride is to override the chart name. |
| nodeSelector | object | `{}` | nodeSelector constrains a pod to be scheduled on a particular node, more information can be found [here](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/). |
| podAnnotations | object | `{}` | podAnnotations is for setting Kubernetes Annotations to a Pod, more information can be found [here](https://kubernetes.io/docs/concepts/overview/working-with-objects/annotations/). |
| podLabels | object | `{}` | podLabels is for setting Kubernetes Labels to a Pod, more information can be found [here](https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/). |
| podSecurityContext | object | `{}` | podSecurityContext defines privilege and access control settings for a pod, more information can be found [here](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/#set-the-security-context-for-a-pod). |
| postgresql.auth.database | string | `"jesse_db"` | postgresql.database is the database used by Jesse. |
| postgresql.auth.password | string | `"pg-password"` | postgresql.password is the database password used by Jesse. |
| postgresql.auth.username | string | `"jesse_user"` | postgresql.username is the database username used by Jesse. |
| redis.auth.password | string | `"redis-password"` | redis.auth.password is the redis password used by Jesse. |
| replicaCount | int | `1` | replicaCount will set the replicaset count more information can be found [here](https://kubernetes.io/docs/concepts/workloads/controllers/replicaset/). |
| resources | object | `{}` | resources sets the amount of resources the container needs, more information can be found [here](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/). |
| securityContext | object | `{}` | securityContext defines privilege and access control settings for a container, more information can be found [here](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/#set-the-security-context-for-a-container). |
| service.annotations | object | `{}` | service.annotations is for setting Kubernetes Annotations to a Service, more information can be found [here](https://kubernetes.io/docs/concepts/overview/working-with-objects/annotations/). |
| service.port | int | `9000` | service.port sets the port, more information can be found [here](https://kubernetes.io/docs/concepts/services-networking/service/#field-spec-ports). |
| service.type | string | `"ClusterIP"` | service.type sets the service type, more information can be found [here](https://kubernetes.io/docs/concepts/services-networking/service/#publishing-services-service-types). |
| serviceAccount.annotations | object | `{}` | serviceAccount.annotations to add to the service account. |
| serviceAccount.automount | bool | `true` | serviceAccount.automount automatically mounts ServiceAccount's API credentials. |
| serviceAccount.create | bool | `true` | serviceAccount.create specifies whether a service account should be created, more information can be found [here](https://kubernetes.io/docs/concepts/security/service-accounts/). |
| serviceAccount.name | string | `""` | serviceAccount.name is the name of the service account to use. If not set and create is true, a name is generated using the fullname template. |
| tolerations | list | `[]` | tolerations allow the scheduler to schedule pods with matching taints, more information can be found [here](https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/). |
| volumeMounts | list | `[]` | volumeMounts is a list of additional volumeMounts on the output Deployment definition. |
| volumes | list | `[]` | volumes is a list of additional volumes on the output Deployment definition. |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.14.2](https://github.com/norwoodj/helm-docs/releases/v1.14.2)
